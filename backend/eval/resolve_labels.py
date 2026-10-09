"""Bind gold-set text anchors to chunk ids in the live index.

Gold-set labels are text anchors rather than chunk ids, so the set survives
re-chunking. This resolves them against whatever is currently indexed and
writes gold_set_resolved.json, which run_eval.py consumes.

Chunk identity matches the format used at ingestion time, f"{doc_id}_{chunk_id}",
so resolved labels line up directly with what retrieve_chunks returns.

Run after seed_corpus.py, and re-run any time chunking changes. Always read the
coverage report at the end: an anchor resolving to zero chunks means either the
document was not ingested or extraction dropped that passage, and both
invalidate the query.

    $env:CHROMA_PERSIST_DIR = ".\\data\\chroma_eval"
    python eval/resolve_labels.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.vector_store import vector_store  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLD_SET = EVAL_DIR / "gold_set.json"
RESOLVED = EVAL_DIR / "gold_set_resolved.json"


def normalize(text: str) -> str:
    """Collapse whitespace and lowercase, so PDF extraction quirks don't block a match."""
    return re.sub(r"\s+", " ", text or "").lower().strip()


def load_index() -> list[dict]:
    data = vector_store.collection.get(include=["documents", "metadatas"])
    return [
        {
            "chunk_key": f"{meta['doc_id']}_{meta.get('chunk_id')}",
            "doc_id": meta["doc_id"],
            "chunk_id": meta.get("chunk_id"),
            "filename": meta["filename"],
            "page": meta.get("page"),
            "section": meta.get("section", "General"),
            "content_type": meta.get("content_type", "text"),
            "document_type": meta.get("document_type", "general"),
            "norm_text": normalize(text),
        }
        for text, meta in zip(data["documents"], data["metadatas"])
    ]


def resolve_query(query: dict, index: list[dict]) -> dict:
    """Find every chunk containing any anchor, scoped to the query's source files."""
    source_files = [query["source_file"]]
    if query.get("secondary_file"):
        source_files.append(query["secondary_file"])

    scoped = [c for c in index if c["filename"] in source_files]
    anchors = [(raw, normalize(raw)) for raw in query["answer_anchors"]]

    matched: dict[str, dict] = {}
    anchor_hits = {raw: 0 for raw, _ in anchors}

    for chunk in scoped:
        for raw, anchor in anchors:
            if anchor and anchor in chunk["norm_text"]:
                matched[chunk["chunk_key"]] = chunk
                anchor_hits[raw] += 1

    resolved = dict(query)
    resolved["relevant_chunks"] = [
        {
            "chunk_key": c["chunk_key"],
            "filename": c["filename"],
            "page": c["page"],
            "section": c["section"],
            "content_type": c["content_type"],
        }
        for c in matched.values()
    ]
    resolved["anchor_hits"] = anchor_hits
    resolved["chunks_scoped"] = len(scoped)
    return resolved


def main():
    gold = json.loads(GOLD_SET.read_text(encoding="utf-8"))
    index = load_index()

    if not index:
        print("Index is empty. Run seed_corpus.py first.")
        sys.exit(1)

    indexed_files = sorted({c["filename"] for c in index})
    print(f"Index holds {len(index)} chunks across {len(indexed_files)} files:")
    for name in indexed_files:
        chunks = [c for c in index if c["filename"] == name]
        types = sorted({c["document_type"] for c in chunks})
        tables = sum(1 for c in chunks if c["content_type"] == "table")
        print(f"  {name}: {len(chunks)} chunks ({tables} table), classified as {'/'.join(types)}")

    missing = [f for f in gold["corpus"] if f not in indexed_files]
    if missing:
        print(f"\nWARNING: corpus files absent from the index: {missing}")
        print("Queries targeting them will resolve to zero relevant chunks.")

    resolved = [resolve_query(q, index) for q in gold["queries"]]

    unresolved = [r for r in resolved if not r["relevant_chunks"]]
    partial = [
        r for r in resolved
        if r["relevant_chunks"] and any(v == 0 for v in r["anchor_hits"].values())
    ]

    out = dict(gold)
    out["queries"] = resolved
    out["resolution_report"] = {
        "total_queries": len(resolved),
        "fully_resolved": len(resolved) - len(unresolved),
        "unresolved": [r["id"] for r in unresolved],
        "partial_anchor_match": [r["id"] for r in partial],
    }
    RESOLVED.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"\nResolved {len(resolved) - len(unresolved)}/{len(resolved)} queries.")
    if unresolved:
        print("\nUNRESOLVED (fix the anchor or check extraction before trusting the eval):")
        for r in unresolved:
            print(f"  {r['id']}  {r['query'][:58]}  [{r['source_file']}]")
    if partial:
        print(f"\nPartial anchor matches (review, often fine): {[r['id'] for r in partial]}")
    print(f"\nWrote {RESOLVED}")


if __name__ == "__main__":
    main()
