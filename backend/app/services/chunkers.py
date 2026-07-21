"""Type-specific chunking strategies, refactored for page-streaming ingestion.

Each chunker is consumed one page at a time via chunk_page(). Only small
carried state survives between pages (current label, chunk index), so this
stays compatible with the memory-bounded ingestion pipeline.
"""

import re

from app.core.config import settings
from app.services.classification_service import ROW_ID_PATTERN

# ---------------------------------------------------------------- patterns

SOP_HEADING_PATTERN = re.compile(r"^(\d+(\.\d+)*\s+.+|[A-Z][A-Z\s]{3,})$")

# Clause/article/section boundaries, plus annexure-style boundaries --
# contracts commonly embed rate cards / SLA tables as annexures.
CLAUSE_PATTERN = re.compile(
    r"^(Clause\s+\d+(\.\d+)*\b.*"
    r"|Article\s+[IVXLCDM]+\b.*"
    r"|Section\s+\d+(\.\d+)*\b.*"
    r"|(ANNEXURE|SCHEDULE|EXHIBIT|APPENDIX)\s+[A-Z0-9]+\b.*)",
    re.IGNORECASE,
)

FIELD_LINE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9 /_#-]{1,40}):\s*(.+)$")

MAX_TABLE_CHUNK_CHARS = settings.chunk_size * 2
_MD_SEPARATOR_CHARS = set("|-: ")


# ---------------------------------------------------------------- base


class BaseStreamingChunker:
    """Shared machinery: table splitting, chunk construction, id counter,
    and section-pattern text splitting with cross-page label carry-over."""

    section_pattern: re.Pattern | None = SOP_HEADING_PATTERN
    default_label = "General"

    def __init__(self, doc_id, filename, page_count, splitter, document_type="general"):
        self.doc_id = doc_id
        self.filename = filename
        self.page_count = page_count
        self.splitter = splitter
        self.document_type = document_type

        self._label = self.default_label
        self._next_index = 0

    def chunk_page(self, page_number: int, text: str, tables: list[str]) -> list[dict]:
        chunks = []

        for table_md in tables:
            table_md = (table_md or "").strip()
            if not table_md:
                continue
            for piece in self._split_table_keep_header(table_md):
                chunks.append(self._make_chunk(page_number, "Table", piece, "table"))

        text = (text or "").strip()
        if text:
            chunks.extend(self._chunk_text(page_number, text))

        return chunks

    def _chunk_text(self, page_number: int, text: str) -> list[dict]:
        chunks = []

        if self.section_pattern is None:
            for piece in self.splitter.split_text(text):
                if piece.strip():
                    chunks.append(self._make_chunk(page_number, self.default_label, piece, "text"))
            return chunks

        sections = _split_by_pattern(text, self.section_pattern, self.default_label)

        for idx, (label, content) in enumerate(sections):
            # Continuation page (no boundary line yet) inherits the carried label.
            if idx == 0 and label == self.default_label and self._label != self.default_label:
                label = self._label
            else:
                self._label = label

            if not content.strip():
                continue

            for piece in self.splitter.split_text(content):
                if piece.strip():
                    chunks.append(self._make_chunk(page_number, label, piece, "text"))

        return chunks

    def _split_table_keep_header(self, table_md: str) -> list[str]:
        # Re-prepends the markdown header row to every split piece, so no
        # fragment loses its column names.
        if len(table_md) <= MAX_TABLE_CHUNK_CHARS:
            return [table_md]

        lines = table_md.splitlines()
        header = ""
        body = table_md

        if (
            len(lines) >= 3
            and lines[0].lstrip().startswith("|")
            and lines[1].strip()
            and set(lines[1].strip()) <= _MD_SEPARATOR_CHARS
        ):
            header = "\n".join(lines[:2])
            body = "\n".join(lines[2:])

        pieces = self.splitter.split_text(body)
        if not header:
            return [p for p in pieces if p.strip()]
        return [f"{header}\n{p}" for p in pieces if p.strip()]

    def _make_chunk(self, page_number, section, text, content_type):
        chunk = {
            "id": f"{self.doc_id}_{self._next_index}",
            "text": text,
            "metadata": {
                "doc_id": self.doc_id,
                "filename": self.filename,
                "page": page_number,
                "page_count": self.page_count,
                "chunk_id": self._next_index,
                "section": section,
                "char_count": len(text),
                "content_type": content_type,
                "document_type": self.document_type,
            },
        }
        self._next_index += 1
        return chunk


def _split_by_pattern(text: str, pattern: re.Pattern, default_label: str) -> list[tuple[str, str]]:
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


# ---------------------------------------------------------------- strategies


class SOPChunker(BaseStreamingChunker):
    """Heading-based. Fits SOPs/circulars and is the safe default type."""
    section_pattern = SOP_HEADING_PATTERN
    default_label = "General"


class ContractChunker(BaseStreamingChunker):
    """Clause-based, with annexure boundaries. Keeps each clause and each
    embedded annexure (e.g. rate schedules) as its own labeled chunk."""
    section_pattern = CLAUSE_PATTERN
    default_label = "Preamble"


class RateCardChunker(BaseStreamingChunker):
    """Table-first. Section detection is disabled since prose headings are
    unreliable on rate cards; surrounding text is kept as page context."""
    section_pattern = None
    default_label = "Page Context"


class InvoiceChunker(BaseStreamingChunker):
    """Groups 'Field: value' lines into one Invoice Fields chunk per page;
    remaining prose splits normally."""
    default_label = "General"

    def _chunk_text(self, page_number: int, text: str) -> list[dict]:
        chunks = []
        field_lines, other_lines = [], []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            (field_lines if FIELD_LINE_PATTERN.match(line) else other_lines).append(line)

        if field_lines:
            chunks.append(
                self._make_chunk(page_number, "Invoice Fields", "\n".join(field_lines), "text")
            )

        if other_lines:
            for piece in self.splitter.split_text("\n".join(other_lines)):
                if piece.strip():
                    chunks.append(self._make_chunk(page_number, "General", piece, "text"))

        return chunks


class DataLogChunker(BaseStreamingChunker):
    """Splits on row-ID boundaries in the character stream so fused rows
    (a real PyMuPDF extraction artifact) still separate correctly. Records
    are packed into chunk_size batches and never bisected; the column
    header is carried across pages in case continuation pages omit it."""
    default_label = "Data Log"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_header: str | None = None

    def _chunk_text(self, page_number: int, text: str) -> list[dict]:
        header, records = _split_into_records(text)

        if not records:
            return [
                self._make_chunk(page_number, "Data Log", piece, "text")
                for piece in self.splitter.split_text(text)
                if piece.strip()
            ]

        if header:
            self._last_header = header
        header_prefix = f"{self._last_header}\n" if self._last_header else ""

        chunks = []
        batch: list[str] = []
        batch_len = len(header_prefix)

        def flush():
            nonlocal batch, batch_len
            if not batch:
                return
            body = "\n".join(batch)
            chunks.append(
                self._make_chunk(
                    page_number, "Data Log Records",
                    f"{header_prefix}{body}", "data_log_row",
                )
            )
            batch = []
            batch_len = len(header_prefix)

        for record in records:
            record_len = len(record) + 1
            if batch_len + record_len > settings.chunk_size and batch:
                flush()
            batch.append(record)
            batch_len += record_len

        flush()
        return chunks


def _split_into_records(text: str):
    matches = list(ROW_ID_PATTERN.finditer(text))
    if len(matches) < 5:
        return None, []

    header = text[: matches[0].start()].strip() or None
    records = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        record = text[start:end].strip()
        if record:
            records.append(record)
    return header, records


# ---------------------------------------------------------------- registry

CHUNKER_REGISTRY: dict[str, type[BaseStreamingChunker]] = {
    "sop": SOPChunker,
    "contract": ContractChunker,
    "rate_card": RateCardChunker,
    "invoice": InvoiceChunker,
    "data_log": DataLogChunker,
    "general": SOPChunker,
}


def make_chunker(
    doc_type: str,
    *,
    doc_id: str,
    filename: str,
    page_count: int,
    splitter,
) -> BaseStreamingChunker:
    # Unknown types fall back to SOPChunker so misclassification never
    # produces worse chunks than the original single-strategy pipeline.
    cls = CHUNKER_REGISTRY.get(doc_type, SOPChunker)
    return cls(
        doc_id=doc_id,
        filename=filename,
        page_count=page_count,
        splitter=splitter,
        document_type=doc_type if doc_type in CHUNKER_REGISTRY else "general",
    )