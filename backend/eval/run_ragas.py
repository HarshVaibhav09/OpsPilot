"""Phase 2 of the RAGAS eval: score the generated answers.

Standalone by design. This reads ragas_inputs.json and a .env file, and imports
nothing from the app. That decoupling is deliberate: ragas pins an older
LangChain than the application does, so the scorer runs in its own virtual
environment and its dependency conflicts never reach the app.

Four metrics, split across the two failure modes:

  faithfulness      - is every claim in the answer supported by the retrieved
                      context. The direct hallucination measure.
  answer_relevancy  - does the answer address the question asked, rather than
                      being true but beside the point.
  context_precision - are the retrieved chunks relevant, or is context budget
                      wasted on noise.
  context_recall    - did retrieval surface everything the ground truth needed.

Setup, from the backend directory:

    python -m venv .venv-eval
    .\\.venv-eval\\Scripts\\Activate.ps1
    pip install -r eval/requirements-eval.txt
    python eval/run_ragas.py --limit 5

Phase 1 (generate_answers.py) runs in the normal app venv. Only this script
runs in .venv-eval.
"""

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent
INPUTS = EVAL_DIR / "ragas_inputs.json"
RESULTS_JSON = EVAL_DIR / "ragas_results.json"
RESULTS_MD = EVAL_DIR / "RAGAS_RESULTS.md"
SCORES = EVAL_DIR / "ragas_scores.json"   # per-record checkpoint, survives quota walls

METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

DEFAULT_JUDGE = "openai/gpt-oss-120b"
DEFAULT_EMBEDDING = "BAAI/bge-small-en-v1.5"


def load_env() -> dict:
    """Read backend/.env without importing the app's settings module.

    utf-8-sig rather than utf-8, so a BOM written by a Windows editor does not
    end up glued to the first key name."""
    env_path = BACKEND_DIR / ".env"
    values = {}

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")

    # Real environment variables win, matching pydantic-settings precedence.
    for key in list(values) + ["LLM_API_KEY", "LLM_MODEL", "EMBEDDING_MODEL"]:
        if os.environ.get(key):
            values[key] = os.environ[key]

    return values


def build_judge(env: dict, override_model: str | None = None):
    """Point ragas at the app's own LLM provider and local embedding model
    instead of its OpenAI default, so scoring costs nothing extra and uses the
    same generation stack the answers came from.

    Key names follow the app's provider-agnostic convention (LLM_API_KEY,
    LLM_MODEL) rather than naming a vendor."""
    from langchain_groq import ChatGroq
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    api_key = env.get("LLM_API_KEY")
    if not api_key:
        print("LLM_API_KEY not found in backend/.env or the environment.")
        print(f"Keys parsed from .env: {sorted(env)}")
        sys.exit(1)

    provider = (env.get("LLM_PROVIDER") or "groq").lower()
    if provider != "groq":
        print(f"LLM_PROVIDER is '{provider}', but this scorer only wires up Groq.")
        print("Swap ChatGroq in build_judge for the matching LangChain chat model.")
        sys.exit(1)

    judge_model = override_model or env.get("LLM_MODEL") or DEFAULT_JUDGE
    embedding_model = env.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING

    # langchain-groq 0.1.5 sums token-usage fields across generations with +=.
    # Groq now nests dicts inside token_usage (prompt_tokens_details and
    # friends), so that summation raises TypeError. It only fires on metrics
    # that request multiple generations, which is why answer_relevancy fails
    # every time while faithfulness mostly survives. Token accounting is not
    # used here, so returning an empty dict is a safe way around it.
    ChatGroq._combine_llm_outputs = lambda self, llm_outputs: {}

    llm = LangchainLLMWrapper(ChatGroq(
        model=judge_model,
        api_key=api_key,
        temperature=0.0,   # judging must be deterministic
        max_retries=5,     # free-tier rate limits are bursty
    ))
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=embedding_model)
    )
    return llm, embeddings, judge_model, embedding_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only score the first N records")
    parser.add_argument("--workers", type=int, default=2,
                        help="parallel judge calls; keep low for rate-limited providers")
    parser.add_argument("--judge-model",
                        help="override LLM_MODEL for judging. gpt-oss-120b has a "
                             "200k token/day free-tier cap that a 50-record run "
                             "exceeds; llama-3.1-8b-instant has a far higher cap.")
    parser.add_argument("--resume", action="store_true",
                        help="skip records already scored in ragas_scores.json")
    parser.add_argument("--timeout", type=int, default=600,
                        help="per-job timeout in seconds")
    args = parser.parse_args()

    if not INPUTS.exists():
        print("ragas_inputs.json not found. Run generate_answers.py in the app venv first.")
        raise SystemExit(1)

    from datasets import Dataset
    from ragas import evaluate
    from ragas.run_config import RunConfig
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )

    env = load_env()
    payload = json.loads(INPUTS.read_text(encoding="utf-8"))
    records = [r for r in payload["records"] if r["contexts"]]
    dropped = [r["id"] for r in payload["records"] if not r["contexts"]]

    prior = {}
    if args.resume and SCORES.exists():
        prior = json.loads(SCORES.read_text(encoding="utf-8"))
        before = len(records)
        records = [r for r in records if r["id"] not in prior]
        print(f"Resuming: {before - len(records)} records already scored, "
              f"{len(records)} remaining.\n")

    if args.limit:
        records = records[: args.limit]

    if not records:
        print("Nothing left to score. Re-run without --resume to rescore everything.")
        raise SystemExit(0)

    if dropped:
        print(f"Excluding {len(dropped)} records that retrieved no context: {dropped}")
        print("Those are retrieval failures, already counted in recall@5. Scoring them "
              "here would conflate retrieval and generation quality.\n")

    dataset = Dataset.from_dict({
        "question": [r["query"] for r in records],
        "answer": [r["answer"] for r in records],
        "contexts": [r["contexts"] for r in records],
        "ground_truth": [r["ground_truth"] for r in records],
    })

    llm, embeddings, judge_model, embedding_model = build_judge(env, args.judge_model)

    print(f"Scoring {len(records)} records with judge={judge_model} ...")
    print(f"{len(records) * 4} jobs at {args.workers} worker(s). "
          f"Throttled deliberately: the judge provider rate-limits, and ragas's "
          f"default of 16 parallel workers just queues requests until they time out.\n")

    # ragas defaults to max_workers=16 and timeout=180. Against a rate-limited
    # endpoint those workers serialise behind the limit and most jobs die on
    # timeout rather than on any real failure. Fewer workers plus a longer
    # timeout is slower in wall-clock terms but actually completes.
    run_config = RunConfig(
        timeout=args.timeout,
        max_workers=args.workers,
        max_retries=10,
        max_wait=90,
    )

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
        raise_exceptions=False,   # one bad parse should not kill the run
    )

    df = result.to_pandas()
    for i, record in enumerate(records):
        for metric in METRIC_NAMES:
            if metric in df.columns:
                value = df.iloc[i][metric]
                record[metric] = None if value != value else round(float(value), 3)

    # Checkpoint every scored record immediately. A daily token quota can end a
    # run mid-way, and regenerating scores already paid for is pure waste.
    persisted = dict(prior)
    for record in records:
        if any(record.get(m) is not None for m in METRIC_NAMES):
            persisted[record["id"]] = {m: record.get(m) for m in METRIC_NAMES}
    SCORES.write_text(json.dumps(persisted, indent=2), encoding="utf-8")

    # Fold checkpointed scores back in so the report covers every record ever
    # scored, not only this run's slice.
    all_records = [r for r in payload["records"] if r["contexts"]]
    by_id = {r["id"]: r for r in records}
    records = []
    for r in all_records:
        merged = dict(by_id.get(r["id"], r))
        if r["id"] in persisted:
            merged.update(persisted[r["id"]])
        if any(merged.get(m) is not None for m in METRIC_NAMES):
            records.append(merged)

    def mean_of(rows, metric):
        values = [r[metric] for r in rows if r.get(metric) is not None]
        return round(statistics.mean(values), 3) if values else None

    def coverage_of(rows, metric):
        return sum(1 for r in rows if r.get(metric) is not None)

    overall = {m: mean_of(records, m) for m in METRIC_NAMES}
    coverage = {m: coverage_of(records, m) for m in METRIC_NAMES}

    # A metric averaged over two surviving jobs looks identical to one averaged
    # over fifty unless coverage is stated outright. Timeouts silently shrink
    # the denominator, so this check is the difference between a result and a
    # rounding artifact.
    incomplete = {m: c for m, c in coverage.items() if c < len(records)}
    if incomplete:
        print("\nWARNING: incomplete metric coverage. Judge jobs failed or timed out.")
        for metric, scored in incomplete.items():
            print(f"  {metric:<18} scored {scored}/{len(records)}")
        print("Re-run with fewer workers (--workers 1) or a longer timeout before "
              "trusting these averages.\n")

    by_style = defaultdict(list)
    for r in records:
        by_style[r["query_type"]].append(r)
    per_style = {
        s: {"n": len(rows), **{m: mean_of(rows, m) for m in METRIC_NAMES}}
        for s, rows in by_style.items()
    }

    by_doc = defaultdict(list)
    for r in records:
        by_doc[r["document_type"]].append(r)
    per_doc = {
        d: {"n": len(rows), **{m: mean_of(rows, m) for m in METRIC_NAMES}}
        for d, rows in by_doc.items()
    }

    RESULTS_JSON.write_text(json.dumps({
        "judge_model": judge_model,
        "embedding_model": embedding_model,
        "hybrid": payload["hybrid"],
        "scored": len(records),
        "excluded_no_context": dropped,
        "overall": overall,
        "coverage": coverage,
        "by_query_type": per_style,
        "by_document_type": per_doc,
        "per_record": records,
    }, indent=2), encoding="utf-8")

    RESULTS_MD.write_text(build_markdown(
        overall, coverage, per_style, per_doc, records, dropped,
        judge_model, payload["hybrid"]
    ), encoding="utf-8")

    print("\nOverall:")
    for metric, value in overall.items():
        scored = sum(1 for r in records if r.get(metric) is not None)
        flag = "" if scored == len(records) else f"   <- only {scored}/{len(records)} scored"
        print(f"  {metric:<18} {value}{flag}")

    incomplete = [m for m in METRIC_NAMES
                  if sum(1 for r in records if r.get(m) is not None) < len(records)]
    if incomplete:
        print("\nSome jobs did not return a score, usually a timeout against a rate-limited "
              "judge. Re-run with --workers 1 and a longer --timeout before trusting these "
              "averages: a metric computed over a subset is not comparable to one computed "
              "over all records.")

    print(f"\nWrote {RESULTS_JSON} and {RESULTS_MD}")


def build_markdown(overall, coverage, per_style, per_doc, records, dropped,
                   judge_model, hybrid):
    def cell(v):
        return "n/a" if v is None else f"{v}"

    lines = [
        "# OpsPilot Generation Evaluation (RAGAS)",
        "",
        f"Scored {len(records)} of 50 gold-set queries. Retrieval mode: "
        f"{'hybrid' if hybrid else 'dense only'}. Judge: `{judge_model}`.",
        "",
        "Answers were generated through the live chat pipeline, and the contexts scored here "
        "are the exact chunks that produced each answer, not a separate retrieval pass.",
        "",
        "## Overall",
        "",
        "| Metric | Score | Scored | What it measures |",
        "|---|---|---|---|",
        f"| Faithfulness | {cell(overall['faithfulness'])} | {coverage['faithfulness']}/{len(records)} | Every claim in the answer is supported by the retrieved context. The direct hallucination measure. |",
        f"| Answer relevancy | {cell(overall['answer_relevancy'])} | {coverage['answer_relevancy']}/{len(records)} | The answer addresses the question asked, rather than being true but beside the point. |",
        f"| Context precision | {cell(overall['context_precision'])} | {coverage['context_precision']}/{len(records)} | Retrieved chunks are relevant, rather than padding context with noise. |",
        f"| Context recall | {cell(overall['context_recall'])} | {coverage['context_recall']}/{len(records)} | Retrieval surfaced everything the ground-truth answer needed. |",
        "",
        "Faithfulness and answer relevancy are generation-side; context precision and recall are "
        "retrieval-side. Keeping both in view separates a hallucinating generator from one that "
        "was handed the wrong context.",
        "",
        "## By query style",
        "",
        "| Query style | n | Faithfulness | Answer relevancy | Context precision | Context recall |",
        "|---|---|---|---|---|---|",
    ]

    for style in sorted(per_style):
        s = per_style[style]
        lines.append(
            f"| {style} | {s['n']} | {cell(s['faithfulness'])} | {cell(s['answer_relevancy'])} | "
            f"{cell(s['context_precision'])} | {cell(s['context_recall'])} |"
        )

    lines += ["", "## By document type", "",
              "| Document type | n | Faithfulness | Answer relevancy | Context precision | Context recall |",
              "|---|---|---|---|---|---|"]

    for doc in sorted(per_doc):
        d = per_doc[doc]
        lines.append(
            f"| {doc} | {d['n']} | {cell(d['faithfulness'])} | {cell(d['answer_relevancy'])} | "
            f"{cell(d['context_precision'])} | {cell(d['context_recall'])} |"
        )

    weak = sorted(
        (r for r in records if r.get("faithfulness") is not None),
        key=lambda r: r["faithfulness"],
    )[:5]

    lines += ["", "## Lowest faithfulness scores", "",
              "Worth reading by hand: these are where the generator drifted furthest from "
              "its context.", "",
              "| Query | Faithfulness | Answer relevancy |", "|---|---|---|"]
    for r in weak:
        lines.append(
            f"| {r['id']}: {r['query'][:52]} | {cell(r['faithfulness'])} | "
            f"{cell(r['answer_relevancy'])} |"
        )

    lines += [
        "",
        "## Known limitations",
        "",
        f"- The judge is `{judge_model}`, a mid-size open model rather than a frontier one. "
        "RAGAS scores are judge-dependent, so these are not directly comparable to published "
        "benchmarks run with GPT-4-class judges. They are internally consistent, which is what "
        "makes them useful for tracking change over time.",
        "- Faithfulness measures grounding in the retrieved context, not truth. An answer "
        "faithfully derived from a wrong chunk still scores well. Retrieval quality is measured "
        "separately in RESULTS.md.",
    ]

    if dropped:
        lines.append(
            f"- {len(dropped)} queries retrieved no context and were excluded: {dropped}. Those "
            "are retrieval failures already captured by recall@5; scoring them as generation "
            "failures would double-count them."
        )

    lines += [
        "- Ground truths are short factual statements written by hand from the source documents. "
        "Context recall is therefore stricter on multi-part answers, where one missing detail "
        "lowers the score.",
        "- The scorer runs in a separate virtual environment (.venv-eval) because ragas pins an "
        "older LangChain than the application. See eval/requirements-eval.txt for the exact set.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()