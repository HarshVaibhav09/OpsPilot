"""Phase 1 of the RAGAS eval: generate answers through the real pipeline.

Runs every gold-set query through handle_chat_message with developer_mode on,
which returns both the generated answer and the exact chunks that produced it.
Writes ragas_inputs.json as a checkpoint so phase 2 (scoring) can be re-run
without regenerating anything.

Each query gets a fresh session id. This matters: handle_chat_message rewrites
the query against recent history, so reusing one session would let query 12
contaminate query 13's rewrite and the eval would measure conversation drift
rather than retrieval and generation quality.

    $env:CHROMA_PERSIST_DIR = ".\\data\\chroma_eval"
    python eval/generate_answers.py
    python eval/generate_answers.py --limit 5     # smoke test first
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chat_service import handle_chat_message  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_SET = EVAL_DIR / "gold_set.json"
OUTPUT = EVAL_DIR / "ragas_inputs.json"

REQUEST_DELAY_S = 1.0  # keeps well under Groq's free-tier rate limit


def generate_one(query: dict, hybrid: bool) -> dict:
    """One query, one throwaway session, no history carried in."""
    response = handle_chat_message(
        session_id=f"ragas-{uuid.uuid4().hex[:12]}",
        message=query["query"],
        developer_mode=True,
        hybrid_search=hybrid,
    )

    dev = response.get("developer") or {}
    chunks = dev.get("retrieved_chunks", [])

    return {
        "id": query["id"],
        "query": query["query"],
        "query_type": query["query_type"],
        "document_type": query["document_type"],
        "answer": response["answer"],
        "contexts": [c["text"] for c in chunks],
        "ground_truth": query["expected_answer"],
        "confidence": response["confidence"],
        "rewritten_query": dev.get("rewritten_query"),
        "avg_similarity": dev.get("avg_similarity"),
        "citation_count": len(response.get("citations", [])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only run the first N queries")
    parser.add_argument("--dense", action="store_true", help="disable hybrid retrieval")
    args = parser.parse_args()

    gold = json.loads(GOLD_SET.read_text(encoding="utf-8"))
    queries = gold["queries"][: args.limit] if args.limit else gold["queries"]
    hybrid = not args.dense

    print(f"Generating answers for {len(queries)} queries (hybrid={hybrid}) ...")

    records, failures = [], []
    for i, query in enumerate(queries, 1):
        try:
            record = generate_one(query, hybrid)
            records.append(record)
            status = "OK " if record["contexts"] else "NO CONTEXT"
            print(f"  [{i:>2}/{len(queries)}] {record['id']}  {status}  "
                  f"{len(record['contexts'])} chunks, conf={record['confidence']}")
        except Exception as e:
            failures.append({"id": query["id"], "error": str(e)})
            print(f"  [{i:>2}/{len(queries)}] {query['id']}  FAILED: {e}")

        time.sleep(REQUEST_DELAY_S)

    OUTPUT.write_text(json.dumps({
        "hybrid": hybrid,
        "generated": len(records),
        "failures": failures,
        "records": records,
    }, indent=2), encoding="utf-8")

    empty = [r["id"] for r in records if not r["contexts"]]
    print(f"\nGenerated {len(records)}/{len(queries)}.")
    if empty:
        print(f"Queries that retrieved nothing (will be excluded from scoring): {empty}")
    if failures:
        print(f"Failures: {[f['id'] for f in failures]}")
    print(f"\nWrote {OUTPUT}")
    print("Next: python eval/run_ragas.py")


if __name__ == "__main__":
    main()