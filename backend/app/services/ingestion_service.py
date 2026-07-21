import gc
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import uuid

import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.db.vector_store import vector_store
from app.services.chunkers import make_chunker
from app.services.classification_service import classify_document
from app.services.embedding_service import embed_documents

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)

STORAGE_BATCH_SIZE = settings.embed_batch_size
MAX_TABLE_CHUNK_CHARS = settings.chunk_size * 2

# The contradiction-analysis step only looks at the first 100 chunks anyway
# (MAX_ANALYSIS_CHUNKS in document_analysis_service.py).
MAX_CHUNKS_KEPT_FOR_ANALYSIS = 100

# classify_document() itself samples pages[:5] -- buffering exactly this many
# pages up front is enough to classify without materializing the document.
CLASSIFICATION_SAMPLE_PAGES = 5


def _page_may_have_tables(page: fitz.Page) -> bool:
    """Skips the slow table-detection pass on pages with no drawn lines."""
    try:
        return len(page.get_drawings()) > 0
    except Exception:
        return True


def _extract_page(page: fitz.Page) -> tuple[str, list[str]]:
    tables = []
    if _page_may_have_tables(page):
        try:
            for table in page.find_tables():
                try:
                    markdown = table.to_markdown()
                    if markdown and markdown.strip():
                        tables.append(markdown.strip())
                except Exception:
                    continue
        except Exception:
            pass

    return page.get_text("text"), tables


def _embed_and_store(chunks: list[dict]) -> None:
    embeddings = embed_documents(
        [c["text"] for c in chunks],
        batch_size=STORAGE_BATCH_SIZE,
    )
    vector_store.add_chunks(
        ids=[c["id"] for c in chunks],
        texts=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )
    del embeddings


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    """Extract, classify, chunk, embed and store a PDF.

    A small sample of pages is buffered up front to classify the document
    type, then the matching chunker streams the rest one page at a time --
    peak memory stays flat regardless of document size, same as before.
    """
    doc_id = str(uuid.uuid4())
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    page_count = doc.page_count
    if page_count > settings.max_pages:
        doc.close()
        raise ValueError(
            f"'{filename}' has {page_count} pages, which exceeds the "
            f"{settings.max_pages}-page limit for this deployment. "
            f"Please split it into smaller files and upload separately."
        )

    found_any_content = False
    total_chunk_count = 0
    table_chunk_count = 0
    pending: list[dict] = []
    kept_for_analysis: list[dict] = []

    def _flush_full_batches():
        nonlocal pending
        while len(pending) >= STORAGE_BATCH_SIZE:
            batch, pending[:] = pending[:STORAGE_BATCH_SIZE], pending[STORAGE_BATCH_SIZE:]
            _embed_and_store(batch)

    # ---------- Phase 1: buffer a small sample to classify ----------
    page_iter = enumerate(doc)
    buffered: list[tuple[int, str, list[str]]] = []
    sample_for_classifier: list[dict] = []

    for i, page in page_iter:
        text, tables = _extract_page(page)
        if text.strip() or tables:
            found_any_content = True

        buffered.append((i + 1, text, tables))
        sample_for_classifier.append({"text": text, "tables": tables})

        if len(buffered) >= CLASSIFICATION_SAMPLE_PAGES:
            break

    document_type = (
        classify_document(sample_for_classifier) if sample_for_classifier else "general"
    )
    del sample_for_classifier

    chunker = make_chunker(
        document_type,
        doc_id=doc_id,
        filename=filename,
        page_count=page_count,
        splitter=_splitter,
    )

    def _process_page(page_number, text, tables):
        nonlocal total_chunk_count, table_chunk_count
        page_chunks = chunker.chunk_page(page_number, text, tables)

        for c in page_chunks:
            total_chunk_count += 1
            if c["metadata"]["content_type"] == "table":
                table_chunk_count += 1
            if len(kept_for_analysis) < MAX_CHUNKS_KEPT_FOR_ANALYSIS:
                kept_for_analysis.append(c)

        pending.extend(page_chunks)

    # ---------- Phase 2: chunk the buffered sample through the router ----------
    for page_number, text, tables in buffered:
        _process_page(page_number, text, tables)
        _flush_full_batches()
    del buffered

    # ---------- Phase 3: stream every remaining page ----------
    for i, page in page_iter:
        text, tables = _extract_page(page)
        if text.strip() or tables:
            found_any_content = True

        _process_page(i + 1, text, tables)
        del text, tables
        _flush_full_batches()

    doc.close()

    if pending:
        _embed_and_store(pending)

    if not found_any_content:
        raise ValueError(f"No extractable text found in '{filename}'.")

    if total_chunk_count == 0:
        raise ValueError(f"No usable chunks generated for '{filename}'.")

    result = {
        "doc_id": doc_id,
        "filename": filename,
        "page_count": page_count,
        "chunk_count": total_chunk_count,
        "table_chunk_count": table_chunk_count,
        "document_type": document_type,
        "has_conflicts": False,
        "chunks": kept_for_analysis,
    }

    gc.collect()
    return result