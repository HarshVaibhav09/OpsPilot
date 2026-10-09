"""Ingest the eval corpus into an isolated index.

OpsPilot ingests on upload, so the eval needs its own reproducible corpus
rather than depending on whatever a user happens to have left in the app.
This calls the ingestion service directly, bypassing the API and the job
queue, and writes into a separate Chroma directory so eval data never mixes
with real uploads.

Point CHROMA_PERSIST_DIR at the eval index before running anything in this
folder. The env var must be set before app.core.config is imported, which is
why it is set at the top of this file rather than in a shell wrapper:

    python eval/seed_corpus.py            # ingest, or skip if already present
    python eval/seed_corpus.py --rebuild  # wipe and re-ingest

Then, in the same shell:

    CHROMA_PERSIST_DIR=./data/chroma_eval python eval/resolve_labels.py
    CHROMA_PERSIST_DIR=./data/chroma_eval python eval/run_eval.py
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[0]
EVAL_INDEX = REPO_ROOT / "data" / "chroma_eval"
CORPUS_DIR = EVAL_DIR / "corpus"

# Must be set before any app import, since Settings reads env at import time.
os.environ.setdefault("CHROMA_PERSIST_DIR", str(EVAL_INDEX))

sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.vector_store import vector_store  # noqa: E402
from app.services.ingestion_service import ingest_document  # noqa: E402

EXPECTED = [
    "sop_vantage_freight.pdf",
    "rate_card_vantage_freight.pdf",
    "vendor_contract_silverline.pdf",
    "safety_incidents.pdf",
    "invoice_statement_vantage.pdf",
]


def guard_index_path():
    """Refuse to run against the live index. Losing real uploads to an eval
    rebuild would be a bad afternoon."""
    resolved = Path(settings.chroma_persist_dir).resolve()
    if "eval" not in resolved.name:
        print(f"Refusing to run: CHROMA_PERSIST_DIR is {resolved}, which is not an eval index.")
        print("Set CHROMA_PERSIST_DIR to ./data/chroma_eval and retry.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="wipe the eval index first")
    args = parser.parse_args()

    guard_index_path()

    if args.rebuild and EVAL_INDEX.exists():
        print(f"Wiping {EVAL_INDEX}")
        shutil.rmtree(EVAL_INDEX)
        print("Re-run without --rebuild in a fresh process to re-ingest.")
        print("(The Chroma client is already bound to the deleted directory.)")
        sys.exit(0)

    if not CORPUS_DIR.exists():
        print(f"Missing {CORPUS_DIR}. Put the five corpus PDFs there:")
        for f in EXPECTED:
            print(f"  {f}")
        sys.exit(1)

    already = {d["filename"] for d in vector_store.list_documents()}
    if already:
        print(f"Eval index already holds: {sorted(already)}")

    for filename in EXPECTED:
        path = CORPUS_DIR / filename

        if not path.exists():
            print(f"  MISSING  {filename}")
            continue

        if filename in already:
            print(f"  skip     {filename} (already ingested)")
            continue

        print(f"  ingesting {filename} ...", end=" ", flush=True)
        try:
            result = ingest_document(path.read_bytes(), filename)
            print(
                f"OK  type={result['document_type']}  "
                f"pages={result['page_count']}  chunks={result['chunk_count']}  "
                f"tables={result['table_chunk_count']}"
            )
        except Exception as e:
            print(f"FAILED: {e}")

    print("\nFinal index contents:")
    for doc in vector_store.list_documents():
        print(
            f"  {doc['filename']}: {doc['chunk_count']} chunks, "
            f"classified as {doc['document_type']}"
        )

    print(f"\nEval index at {EVAL_INDEX}")
    print("Next: CHROMA_PERSIST_DIR=./data/chroma_eval python eval/resolve_labels.py")


if __name__ == "__main__":
    main()