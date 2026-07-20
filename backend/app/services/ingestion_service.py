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

# Save to the vector store in small groups instead of all at once.
# Keeps memory usage low no matter how big the document is.
STORAGE_BATCH_SIZE = 16


def _page_may_have_tables(page: fitz.Page) -> bool:
    """Quick check before running full table detection (which is slow).

    A page with zero drawn lines/shapes can't have a bordered table,
    so we skip the expensive check for it. Might miss a rare table
    made only of aligned text with no visible borders — acceptable
    trade-off for the speed/memory saved on every other page.
    """
    try:
        return len(page.get_drawings()) > 0
    except Exception:
        return True  # not sure? better to check than skip


def extract_pages(file_bytes: bytes) -> list[dict]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []

    for i, page in enumerate(doc):
        table_markdown_blocks = []

        if _page_may_have_tables(page):
            try:
                tables = page.find_tables()
                for table in tables:
                    try:
                        markdown = table.to_markdown()
                        if markdown and markdown.strip():
                            table_markdown_blocks.append(markdown.strip())
                    except Exception:
                        continue
            except Exception:
                table_markdown_blocks = []

        pages.append(
            {
                "page_number": i + 1,
                "text": page.get_text("text"),
                "tables": table_markdown_blocks,
            }
        )

    doc.close()
    return pages


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


def chunk_pages(
    pages: list[dict],
    filename: str,
    doc_id: str,
) -> list[dict]:

    chunks = []
    current_heading = "General"

    for page in pages:
        has_text = bool(page["text"].strip())
        has_tables = bool(page.get("tables"))

        if not has_text and not has_tables:
            continue

        for table_md in page.get("tables", []):
            chunks.append(
                {
                    "id": f"{doc_id}_{len(chunks)}",
                    "text": table_md,
                    "metadata": {
                        "doc_id": doc_id,
                        "filename": filename,
                        "page": page["page_number"],
                        "page_count": len(pages),
                        "chunk_id": len(chunks),
                        "section": "Table",
                        "char_count": len(table_md),
                        "content_type": "table",
                    },
                }
            )

        if has_text:
            page_sections = split_sections(page["text"])

            for idx, (section, content) in enumerate(page_sections):
                if idx == 0 and section == "General" and current_heading != "General":
                    section = current_heading
                else:
                    current_heading = section

                if not content.strip():
                    continue

                for chunk in _splitter.split_text(content):
                    if not chunk.strip():
                        continue
                    chunks.append(
                        {
                            "id": f"{doc_id}_{len(chunks)}",
                            "text": chunk,
                            "metadata": {
                                "doc_id": doc_id,
                                "filename": filename,
                                "page": page["page_number"],
                                "page_count": len(pages),
                                "chunk_id": len(chunks),
                                "section": section,
                                "char_count": len(chunk),
                                "content_type": "text",
                            },
                        }
                    )

    return chunks


def embed_and_store_chunks(chunks: list[dict]) -> None:
    """Embed chunks and save them, a small batch at a time.

    Before: all chunks were embedded in one go and saved in one go —
    memory used grew with the size of the document (this is what
    crashed on a 34-page file with a 512MB server). Now: embed a
    small batch, save it, throw it away, repeat. Peak memory stays
    the same no matter how big the document is.
    """
    for i in range(0, len(chunks), STORAGE_BATCH_SIZE):
        batch = chunks[i : i + STORAGE_BATCH_SIZE]

        batch_embeddings = embed_documents(
            [c["text"] for c in batch],
            batch_size=STORAGE_BATCH_SIZE,
        )

        vector_store.add_chunks(
            ids=[c["id"] for c in batch],
            texts=[c["text"] for c in batch],
            embeddings=batch_embeddings,
            metadatas=[c["metadata"] for c in batch],
        )

        del batch_embeddings


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    doc_id = str(uuid.uuid4())

    pages = extract_pages(file_bytes)

    if len(pages) > settings.max_pages:
        raise ValueError(
            f"'{filename}' has {len(pages)} pages, which exceeds the "
            f"{settings.max_pages}-page limit for this deployment. "
            f"Please split it into smaller files and upload separately."
        )

    has_any_content = any(
        page["text"].strip() or page.get("tables") for page in pages
    )
    if not has_any_content:
        raise ValueError(f"No extractable text found in '{filename}'.")

    chunks = chunk_pages(
        pages=pages,
        filename=filename,
        doc_id=doc_id,
    )

    # Don't need the raw page data anymore -- free it before the
    # memory-heavy embedding step starts.
    page_count = len(pages)
    del pages

    if not chunks:
        raise ValueError(f"No usable chunks generated for '{filename}'.")

    embed_and_store_chunks(chunks)

    table_chunk_count = sum(1 for c in chunks if c["metadata"]["content_type"] == "table")

    result = {
        "doc_id": doc_id,
        "filename": filename,
        "page_count": page_count,
        "chunk_count": len(chunks),
        "table_chunk_count": table_chunk_count,
        "has_conflicts": False,  # contradiction analysis runs separately, in the background
        "chunks": chunks,
    }

    gc.collect()

    return result