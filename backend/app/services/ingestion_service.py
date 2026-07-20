import gc
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import re
import uuid

import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.db.vector_store import vector_store
from app.services.embedding_service import embed_documents

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)

HEADING_PATTERN = re.compile(r"^(\d+(\.\d+)*\s+.+|[A-Z][A-Z\s]{3,})$")

# How many chunks to embed and save at once. Small and constant no
# matter how big the document is -- this is what keeps memory flat
# whether the file is 5 pages or 500.
STORAGE_BATCH_SIZE = settings.embed_batch_size

# A single dense table (rate card, invoice) can turn into a huge block
# of markdown text. Before, table chunks were stored whole, however
# big, with no size cap. That risks a memory spike on that one chunk
# and silent truncation by the embedding model's token limit. Anything
# bigger than this gets split up like normal text instead.
MAX_TABLE_CHUNK_CHARS = settings.chunk_size * 2

# The contradiction-analysis step only ever looks at the first 100
# chunks of a document anyway (see MAX_ANALYSIS_CHUNKS in
# document_analysis_service.py). No reason to hold every chunk of a
# 500-chunk document in memory just to use the first 100 of them.
MAX_CHUNKS_KEPT_FOR_ANALYSIS = 100


def _page_may_have_tables(page: fitz.Page) -> bool:
    """Quick check before running full table detection (which is slow).

    A page with zero drawn lines/shapes can't have a bordered table,
    so we skip the expensive check for it. Might miss a rare table
    made only of aligned text with no visible borders -- acceptable
    trade-off for the speed/memory saved on every other page.
    """
    try:
        return len(page.get_drawings()) > 0
    except Exception:
        return True  # not sure? better to check than skip


def split_sections(text: str) -> list[tuple[str, str]]:
    sections, heading, buffer = [], "General", []

    for line in filter(None, map(str.strip, text.splitlines())):
        if HEADING_PATTERN.match(line):
            if buffer:
                sections.append((heading, "\n".join(buffer)))
            heading, buffer = line, []
        else:
            buffer.append(line)

    if buffer:
        sections.append((heading, "\n".join(buffer)))

    return sections or [("General", text)]


def _make_chunk(doc_id, filename, page_number, page_count, chunk_index, section, text, content_type):
    return {
        "id": f"{doc_id}_{chunk_index}",
        "text": text,
        "metadata": {
            "doc_id": doc_id,
            "filename": filename,
            "page": page_number,
            "page_count": page_count,
            "chunk_id": chunk_index,
            "section": section,
            "char_count": len(text),
            "content_type": content_type,
        },
    }


def _chunks_for_page(page_number, text, tables, filename, doc_id, page_count, current_heading, next_index):
    """Build every chunk for ONE page (tables + text). Nothing here
    holds data from any other page -- that's what keeps memory bounded
    regardless of how many pages the document has.

    Returns (chunks, updated_heading, updated_next_index).
    """
    chunks = []
    idx = next_index

    for table_md in tables:
        pieces = (
            _splitter.split_text(table_md)
            if len(table_md) > MAX_TABLE_CHUNK_CHARS
            else [table_md]
        )
        for piece in pieces:
            if not piece.strip():
                continue
            chunks.append(_make_chunk(
                doc_id, filename, page_number, page_count, idx, "Table", piece, "table",
            ))
            idx += 1

    if text.strip():
        for s_idx, (section, content) in enumerate(split_sections(text)):
            if s_idx == 0 and section == "General" and current_heading != "General":
                section = current_heading
            else:
                current_heading = section

            if not content.strip():
                continue

            for piece in _splitter.split_text(content):
                if not piece.strip():
                    continue
                chunks.append(_make_chunk(
                    doc_id, filename, page_number, page_count, idx, section, piece, "text",
                ))
                idx += 1

    return chunks, current_heading, idx


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
    """Extract, chunk, embed and store a PDF one page at a time.

    Earlier versions extracted every page into memory first, built
    every chunk for the whole document, THEN embedded everything in
    one batch -- so peak memory grew with document size. This version
    processes and discards one page at a time: a 50-page dense
    logistics file costs roughly the same peak memory as a 5-page one,
    because only one page's worth of data is ever resident at once.
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

    current_heading = "General"
    next_index = 0
    found_any_content = False
    total_chunk_count = 0
    table_chunk_count = 0
    pending: list[dict] = []            # chunks waiting to be embedded
    kept_for_analysis: list[dict] = []  # first 100 chunks, for contradiction analysis

    for i, page in enumerate(doc):
        table_markdown_blocks = []

        if _page_may_have_tables(page):
            try:
                for table in page.find_tables():
                    try:
                        markdown = table.to_markdown()
                        if markdown and markdown.strip():
                            table_markdown_blocks.append(markdown.strip())
                    except Exception:
                        continue
            except Exception:
                pass

        page_text = page.get_text("text")

        if page_text.strip() or table_markdown_blocks:
            found_any_content = True

        page_chunks, current_heading, next_index = _chunks_for_page(
            i + 1, page_text, table_markdown_blocks,
            filename, doc_id, page_count, current_heading, next_index,
        )

        # This page's raw text/tables are no longer needed once its
        # chunks are built -- drop them before moving to the next page.
        del page_text, table_markdown_blocks

        for c in page_chunks:
            total_chunk_count += 1
            if c["metadata"]["content_type"] == "table":
                table_chunk_count += 1
            if len(kept_for_analysis) < MAX_CHUNKS_KEPT_FOR_ANALYSIS:
                kept_for_analysis.append(c)

        pending.extend(page_chunks)
        del page_chunks

        # Flush a full batch to the vector store -- embed, store,
        # discard. Peak memory here stays constant no matter how many
        # pages are still left to process.
        while len(pending) >= STORAGE_BATCH_SIZE:
            batch, pending = pending[:STORAGE_BATCH_SIZE], pending[STORAGE_BATCH_SIZE:]
            _embed_and_store(batch)

    doc.close()

    if pending:
        _embed_and_store(pending)  # flush whatever's left (< one full batch)

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
        "has_conflicts": False,  # contradiction analysis runs separately, in the background
        "chunks": kept_for_analysis,
    }

    gc.collect()
    return result