import re
import uuid

import fitz
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.db.vector_store import vector_store
from app.services.document_analysis_service import analyze_document

_embedder = SentenceTransformer(settings.embedding_model)

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)

HEADING_PATTERN = re.compile(r"^(\d+(\.\d+)*\s+.+|[A-Z][A-Z\s]{3,})$")


def extract_pages(file_bytes: bytes) -> list[dict]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []

    for i, page in enumerate(doc):
        table_markdown_blocks = []
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


def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    return _embedder.encode(
        [c["text"] for c in chunks],
        batch_size=32,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).tolist()


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    doc_id = str(uuid.uuid4())

    pages = extract_pages(file_bytes)

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

    if not chunks:
        raise ValueError(f"No usable chunks generated for '{filename}'.")

    embeddings = embed_chunks(chunks)

    vector_store.add_chunks(
        ids=[c["id"] for c in chunks],
        texts=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )

    analysis = analyze_document(
        doc_id=doc_id,
        filename=filename,
        chunks=chunks,
    )

    table_chunk_count = sum(1 for c in chunks if c["metadata"]["content_type"] == "table")

    return {
        "doc_id": doc_id,
        "filename": filename,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "table_chunk_count": table_chunk_count,
        "has_conflicts": analysis["contradictions"]["has_conflict"],
    }