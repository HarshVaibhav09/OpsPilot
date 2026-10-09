"""Retrieval eval: dense-only against hybrid, recall@5 and MRR.

Runs every resolved gold-set query through retrieve_chunks twice, once with
hybrid disabled and once enabled, and reports the delta overall, by document
type, and by query style. The query-style breakdown is the point: it shows
where hybrid helps rather than only that it does.

    $env:CHROMA_PERSIST_DIR = ".\\data\\chroma_eval"
    python eval/resolve_labels.py
    python eval/run_eval.py
"""

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.retrieval_service import retrieve_chunks  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RESOLVED = EVAL_DIR / "gold_set_resolved.json"
RESULTS_JSON = EVAL_DIR / "results.json"
RESULTS_MD = EVAL_DIR / "RESULTS.md"

K = settings.top_k_final  # score at what the LLM actually sees, not an arbitrary 5


def chunk_key(hit: dict) -> str:
    """Same identity format used at ingestion time."""
    return f"{hit['doc_id']}_{hit['chunk_id']}"


def score_one(retrieved: list[dict], relevant_keys: set[str], k: int = K) -> dict:
    """recall@k: did any relevant chunk land in the top k.
    MRR: reciprocal rank of the first relevant chunk, 0 if none.
    precision@k is computed but not headlined, since anchor-based labelling
    under-counts relevant chunks on multi-record queries and understates it."""
    top = retrieved[:k]
    keys = [chunk_key(h) for h in top]
    hit_ranks = [i + 1 for i, key in enumerate(keys) if key in relevant_keys]

    return {
        "recall_at_k": 1.0 if hit_ranks else 0.0,
        "mrr": 1.0 / hit_ranks[0] if hit_ranks else 0.0,
        "precision_at_k": len(hit_ranks) / len(top) if top else 0.0,
        "first_rank": hit_ranks[0] if hit_ranks else None,
        "retrieved_keys": keys,
    }


def run_mode(queries: list[dict], hybrid: bool) -> list[dict]:
    rows = []
    for q in queries:
        relevant = {c["chunk_key"] for c in q["relevant_chunks"]}
        if not relevant:
            continue

        start = time.perf_counter()
        retrieved = retrieve_chunks(query=q["query"], hybrid=hybrid)
        latency_ms = (time.perf_counter() - start) * 1000

        rows.append({
            "id": q["id"],
            "query": q["query"],
            "query_type": q["query_type"],
            "document_type": q["document_type"],
            "latency_ms": round(latency_ms, 1),
            **score_one(retrieved, relevant),
        })
    return rows


def aggregate(rows: list[dict], key: str | None = None) -> dict:
    groups = {"overall": rows} if key is None else defaultdict(list)
    if key is not None:
        for r in rows:
            groups[r[key]].append(r)

    return {
        name: {
            "n": len(group),
            "recall_at_k": round(statistics.mean(r["recall_at_k"] for r in group), 3),
            "mrr": round(statistics.mean(r["mrr"] for r in group), 3),
            "p50_latency_ms": round(statistics.median(r["latency_ms"] for r in group), 1),
        }
        for name, group in groups.items()
    }


def fmt_delta(dense: float, hybrid: float) -> str:
    d = hybrid - dense
    return f"{'+' if d >= 0 else ''}{d:.3f}"


def build_markdown(dense_rows, hybrid_rows) -> str:
    d_all = aggregate(dense_rows)["overall"]
    h_all = aggregate(hybrid_rows)["overall"]

    lines = [
        "# OpsPilot Retrieval Evaluation",
        "",
        f"50-query hand-labelled gold set over five logistics documents (SOP, rate card, "
        f"vendor contract, incident log, invoice statement). {d_all['n']} queries resolved "
        f"against the live index and scored at k={K}.",
        "",
        f"Recall@{K} asks whether a relevant chunk appeared in the top {K}, which is the number "
        "that matters most: a chunk that is never retrieved cannot be recovered by better "
        f"prompting. MRR asks where it landed, since rank {K} is worth less than rank 1 under a "
        "fixed context budget.",
        "",
        "## Headline",
        "",
        f"| Configuration | Recall@{K} | MRR | p50 latency |",
        "|---|---|---|---|",
        f"| Dense only | {d_all['recall_at_k']} | {d_all['mrr']} | {d_all['p50_latency_ms']} ms |",
        f"| Hybrid (dense + BM25, RRF) | {h_all['recall_at_k']} | {h_all['mrr']} | {h_all['p50_latency_ms']} ms |",
        f"| **Delta** | **{fmt_delta(d_all['recall_at_k'], h_all['recall_at_k'])}** | "
        f"**{fmt_delta(d_all['mrr'], h_all['mrr'])}** | |",
        "",
        "## By query style",
        "",
        "This breakdown explains the headline. Hybrid should win clearly on identifier queries "
        "and roughly tie on paraphrase queries. If it wins uniformly across every style by a "
        "similar margin, suspect a labelling artifact rather than a real gain.",
        "",
        f"| Query style | n | Dense recall@{K} | Hybrid recall@{K} | Delta | Dense MRR | Hybrid MRR |",
        "|---|---|---|---|---|---|---|",
    ]

    d_style, h_style = aggregate(dense_rows, "query_type"), aggregate(hybrid_rows, "query_type")
    for style in sorted(d_style):
        d, h = d_style[style], h_style[style]
        lines.append(
            f"| {style} | {d['n']} | {d['recall_at_k']} | {h['recall_at_k']} | "
            f"{fmt_delta(d['recall_at_k'], h['recall_at_k'])} | {d['mrr']} | {h['mrr']} |"
        )

    lines += ["", "## By document type", "",
              f"| Document type | n | Dense recall@{K} | Hybrid recall@{K} | Delta |",
              "|---|---|---|---|---|"]

    d_doc, h_doc = aggregate(dense_rows, "document_type"), aggregate(hybrid_rows, "document_type")
    for dt in sorted(d_doc):
        d, h = d_doc[dt], h_doc[dt]
        lines.append(
            f"| {dt} | {d['n']} | {d['recall_at_k']} | {h['recall_at_k']} | "
            f"{fmt_delta(d['recall_at_k'], h['recall_at_k'])} |"
        )

    hybrid_by_id = {r["id"]: r for r in hybrid_rows}
    regressions = [
        f"- {r['id']} ({r['query_type']}): {r['query'][:66]}"
        for r in dense_rows
        if (h := hybrid_by_id.get(r["id"])) and h["recall_at_k"] < r["recall_at_k"]
    ]

    lines += ["", "## Queries where hybrid regressed", ""] + (regressions or ["None."])

    lines += [
        "",
        "## Known limitations",
        "",
        "- 50 queries over 5 documents is a regression guard, not a benchmark. It reliably "
        "catches a chunking change that made retrieval worse; it does not support a precise "
        "claim about absolute quality.",
        "- Dense mode retrieves top_k_retrieval candidates; hybrid retrieves twice that before "
        "fusing. Part of the gain therefore comes from the wider candidate pool rather than "
        "from BM25 alone. This mirrors production behaviour, so it is the right thing to "
        "measure, but it does not isolate the fusion step.",
        "- Labels anchor to passages containing the answer. On queries spanning many records "
        f"(all incidents for one truck), recall@{K} is partial by construction, since only some "
        "matching rows can fit in the top results.",
        "- Aggregation and absence queries (largest cargo damage, records missing a truck id) "
        "are included deliberately and are expected to score poorly. Retrieval is the wrong "
        "tool for them; they belong in a structured query path, which is not built yet.",
        "",
    ]
    return "\n".join(lines)


def main():
    if not RESOLVED.exists():
        print("Run resolve_labels.py first.")
        raise SystemExit(1)

    gold = json.loads(RESOLVED.read_text(encoding="utf-8"))
    queries = [q for q in gold["queries"] if q["relevant_chunks"]]
    skipped = [q["id"] for q in gold["queries"] if not q["relevant_chunks"]]

    if skipped:
        print(f"Skipping {len(skipped)} unresolved queries: {skipped}")

    print(f"Evaluating {len(queries)} queries at k={K}, dense only ...")
    dense_rows = run_mode(queries, hybrid=False)

    print(f"Evaluating {len(queries)} queries at k={K}, hybrid ...")
    hybrid_rows = run_mode(queries, hybrid=True)

    RESULTS_JSON.write_text(json.dumps({
        "k": K,
        "dense": {"per_query": dense_rows, "aggregate": aggregate(dense_rows)},
        "hybrid": {"per_query": hybrid_rows, "aggregate": aggregate(hybrid_rows)},
        "by_query_type": {
            "dense": aggregate(dense_rows, "query_type"),
            "hybrid": aggregate(hybrid_rows, "query_type"),
        },
        "by_document_type": {
            "dense": aggregate(dense_rows, "document_type"),
            "hybrid": aggregate(hybrid_rows, "document_type"),
        },
        "skipped": skipped,
    }, indent=2), encoding="utf-8")

    RESULTS_MD.write_text(build_markdown(dense_rows, hybrid_rows), encoding="utf-8")

    d, h = aggregate(dense_rows)["overall"], aggregate(hybrid_rows)["overall"]
    print(f"\n  Dense   recall@{K}={d['recall_at_k']}  MRR={d['mrr']}")
    print(f"  Hybrid  recall@{K}={h['recall_at_k']}  MRR={h['mrr']}")
    print(f"\nWrote {RESULTS_JSON} and {RESULTS_MD}")


if __name__ == "__main__":
    main()
