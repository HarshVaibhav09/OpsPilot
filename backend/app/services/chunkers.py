import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.classification_service import ROW_ID_PATTERN

SOP_HEADING_PATTERN = re.compile(r"^(\d+(\.\d+)*\s+.+|[A-Z][A-Z\s]{3,})$")

CLAUSE_PATTERN = re.compile(
    r"^(Clause\s+\d+(\.\d+)*\b.*|Article\s+[IVXLCDM]+\b.*|Section\s+\d+(\.\d+)*\b.*)",
    re.IGNORECASE,
)

FIELD_LINE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9 /_#-]{1,40}):\s*(.+)$")


def _split_by_pattern(text: str, pattern: re.Pattern, default_label: str) -> list[tuple[str, str]]:
    """Generic section splitter — same logic as the original heading detector,
    but the boundary pattern and default section label are configurable."""
    sections, label, buffer = [], default_label, []

    for line in filter(None, map(str.strip, text.splitlines())):
        if pattern.match(line):
            if buffer:
                sections.append((label, "\n".join(buffer)))
            label, buffer = line, []
        else:
            buffer.append(line)

    if buffer:
        sections.append((label, "\n".join(buffer)))

    return sections or [(default_label, text)]


def _make_chunk(doc_id, filename, page, chunk_index, section, text, content_type, page_count, document_type):
    return {
        "id": f"{doc_id}_{chunk_index}",
        "text": text,
        "metadata": {
            "doc_id": doc_id,
            "filename": filename,
            "page": page,
            "page_count": page_count,
            "chunk_id": chunk_index,
            "section": section,
            "char_count": len(text),
            "content_type": content_type,
            "document_type": document_type,
        },
    }


def _extract_table_chunks(page, doc_id, filename, chunk_count, page_count, document_type):
    chunks = []
    for table_md in page.get("tables", []):
        chunks.append(
            _make_chunk(
                doc_id, filename, page["page_number"], chunk_count + len(chunks),
                "Table", table_md, "table", page_count, document_type,
            )
        )
    return chunks


# ---------- SOP / general: heading-based (original strategy) ----------

def chunk_sop(pages, filename, doc_id, splitter, document_type="sop"):
    chunks = []
    current_heading = "General"

    for page in pages:
        if not page["text"].strip() and not page.get("tables"):
            continue

        chunks.extend(_extract_table_chunks(page, doc_id, filename, len(chunks), len(pages), document_type))

        if not page["text"].strip():
            continue

        sections = _split_by_pattern(page["text"], SOP_HEADING_PATTERN, "General")

        for idx, (heading, content) in enumerate(sections):
            if idx == 0 and heading == "General" and current_heading != "General":
                heading = current_heading
            else:
                current_heading = heading

            if not content.strip():
                continue

            for piece in splitter.split_text(content):
                if not piece.strip():
                    continue
                chunks.append(
                    _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                                heading, piece, "text", len(pages), document_type)
                )

    return chunks


# ---------- Contract: clause-based ----------

def chunk_contract(pages, filename, doc_id, splitter, document_type="contract"):
    chunks = []
    current_clause = "Preamble"

    for page in pages:
        if not page["text"].strip() and not page.get("tables"):
            continue

        chunks.extend(_extract_table_chunks(page, doc_id, filename, len(chunks), len(pages), document_type))

        if not page["text"].strip():
            continue

        sections = _split_by_pattern(page["text"], CLAUSE_PATTERN, "Preamble")

        for idx, (clause, content) in enumerate(sections):
            if idx == 0 and clause == "Preamble" and current_clause != "Preamble":
                clause = current_clause
            else:
                current_clause = clause

            if not content.strip():
                continue

            # Keep clauses whole where possible — splitter only kicks in
            # if a single clause exceeds chunk_size, preserving the clause
            # label on every resulting piece.
            for piece in splitter.split_text(content):
                if not piece.strip():
                    continue
                chunks.append(
                    _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                                clause, piece, "text", len(pages), document_type)
                )

    return chunks


# ---------- Rate card: table-first, no false heading detection ----------

def chunk_rate_card(pages, filename, doc_id, splitter, document_type="rate_card"):
    chunks = []

    for page in pages:
        if not page["text"].strip() and not page.get("tables"):
            continue

        chunks.extend(_extract_table_chunks(page, doc_id, filename, len(chunks), len(pages), document_type))

        # Rate cards are numbers-heavy with unreliable heading structure —
        # skip heading detection entirely and keep any surrounding text
        # (titles, notes, effective dates) as page-context chunks instead
        # of guessing at false section boundaries.
        text = page["text"].strip()
        if text:
            for piece in splitter.split_text(text):
                if not piece.strip():
                    continue
                chunks.append(
                    _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                                "Page Context", piece, "text", len(pages), document_type)
                )

    return chunks


# ---------- Invoice: field extraction ----------

def chunk_invoice(pages, filename, doc_id, splitter, document_type="invoice"):
    chunks = []

    for page in pages:
        if not page["text"].strip() and not page.get("tables"):
            continue

        chunks.extend(_extract_table_chunks(page, doc_id, filename, len(chunks), len(pages), document_type))

        text = page["text"].strip()
        if not text:
            continue

        field_lines = []
        other_lines = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if FIELD_LINE_PATTERN.match(line):
                field_lines.append(line)
            else:
                other_lines.append(line)

        if field_lines:
            field_block = "\n".join(field_lines)
            chunks.append(
                _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                            "Invoice Fields", field_block, "text", len(pages), document_type)
            )

        if other_lines:
            remainder = "\n".join(other_lines)
            for piece in splitter.split_text(remainder):
                if not piece.strip():
                    continue
                chunks.append(
                    _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                                "General", piece, "text", len(pages), document_type)
                )

    return chunks


# ---------- Data log: record-boundary splitting, survives fused rows ----------

def _split_into_records(text: str):
    """Splits on row-ID boundaries directly in the character stream, not on
    newlines — this survives rows that got fused together with no separator
    during PDF text extraction (a real, observed PyMuPDF artifact on dense
    tabular reports), because it never depends on whitespace being present."""
    matches = list(ROW_ID_PATTERN.finditer(text))
    if len(matches) < 5:
        return None, []

    header = text[:matches[0].start()].strip() or None
    records = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        record = text[start:end].strip()
        if record:
            records.append(record)
    return header, records


def chunk_data_log(pages, filename, doc_id, splitter, document_type="data_log"):
    chunks = []

    for page in pages:
        if not page["text"].strip() and not page.get("tables"):
            continue

        chunks.extend(_extract_table_chunks(page, doc_id, filename, len(chunks), len(pages), document_type))

        text = page["text"].strip()
        if not text:
            continue

        header, records = _split_into_records(text)

        if not records:
            # Fallback: no reliable record IDs found on this page, treat as
            # plain text rather than force record-splitting on nothing.
            for piece in splitter.split_text(text):
                if not piece.strip():
                    continue
                chunks.append(
                    _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                                "Data Log", piece, "text", len(pages), document_type)
                )
            continue

        header_prefix = f"{header}\n" if header else ""
        batch: list[str] = []
        batch_len = len(header_prefix)

        def flush():
            nonlocal batch, batch_len
            if not batch:
                return
            body = "\n".join(batch)
            chunk_text = f"{header_prefix}{body}" if header_prefix else body
            chunks.append(
                _make_chunk(doc_id, filename, page["page_number"], len(chunks),
                            "Data Log Records", chunk_text, "data_log_row", len(pages), document_type)
            )
            batch = []
            batch_len = len(header_prefix)

        for record in records:
            record_len = len(record) + 1  # +1 for the joining newline
            if batch_len + record_len > settings.chunk_size and batch:
                flush()
            batch.append(record)
            batch_len += record_len

        flush()

    return chunks


CHUNKER_REGISTRY = {
    "sop": chunk_sop,
    "contract": chunk_contract,
    "rate_card": chunk_rate_card,
    "invoice": chunk_invoice,
    "data_log": chunk_data_log,
    "general": chunk_sop,  # sensible default — same as original behavior
}


def chunk_by_type(
    doc_type: str,
    pages: list[dict],
    filename: str,
    doc_id: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list[dict]:
    chunker = CHUNKER_REGISTRY.get(doc_type, chunk_sop)
    return chunker(pages, filename, doc_id, splitter, document_type=doc_type)