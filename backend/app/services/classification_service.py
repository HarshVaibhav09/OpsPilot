import re

from app.core.llm_client import llm_client

DOCUMENT_TYPES = ["rate_card", "contract", "sop", "invoice", "data_log", "general"]

_KEYWORDS = {
    "rate_card": [
        "rate card", "tariff", "per km", "per unit", "price list",
        "freight rate", "rate per", "surcharge", "fuel adjustment",
    ],
    "contract": [
        "agreement", "whereas", "hereby", "party of the", "governing law",
        "indemnif", "terms and conditions", "clause", "article", "termination",
    ],
    "sop": [
        "standard operating procedure", "sop", "purpose:", "scope:",
        "responsibility", "step 1", "procedure", "checklist",
    ],
    "invoice": [
        "invoice no", "invoice number", "bill to", "subtotal",
        "total due", "amount payable", "gstin", "tax invoice",
    ],
}

_CONFIDENCE_THRESHOLD = 3  # min keyword-hit score before trusting the heuristic

# Matches record-ID-like tokens, e.g. TRK00001, INC00000015, DRV00058, TRIP00036079.
# Used to detect data logs / registers (fleet reports, incident logs, delivery logs)
# structurally, since these documents often lack reliable prose keywords or headings.
ROW_ID_PATTERN = re.compile(r"\b([A-Z]{2,6}\d{4,8})\b")

# If a sample of the document contains at least this many distinct record-ID
# matches, it's treated as a data log regardless of keyword scores — this check
# runs before keyword scoring because it's a structural signal, not a vocabulary
# one, and is more reliable for this document class.
_MIN_ROW_ID_MATCHES = 8


def _looks_like_data_log(text: str) -> bool:
    matches = ROW_ID_PATTERN.findall(text)
    return len(matches) >= _MIN_ROW_ID_MATCHES


def _heuristic_scores(sample_text: str, table_count: int, page_count: int) -> dict[str, float]:
    text = sample_text.lower()
    scores = {doc_type: 0.0 for doc_type in _KEYWORDS}

    for doc_type, keywords in _KEYWORDS.items():
        scores[doc_type] = sum(text.count(kw) for kw in keywords)

    if page_count:
        table_density = table_count / page_count
        scores["rate_card"] += table_density * 5  # dense tables strongly suggest rate cards

    return scores


def classify_document(pages: list[dict]) -> str:
    sample_pages = pages[:5]  # enough signal without processing a whole 50-page doc
    sample_text = "\n".join(p["text"] for p in sample_pages)

    if _looks_like_data_log(sample_text):
        return "data_log"

    table_count = sum(len(p.get("tables", [])) for p in pages)
    scores = _heuristic_scores(sample_text, table_count, len(pages))
    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])

    if best_score >= _CONFIDENCE_THRESHOLD:
        return best_type

    return _classify_with_llm(sample_text) or "general"


def _classify_with_llm(sample_text: str) -> str | None:
    try:
        result = llm_client.generate(
            system_prompt=(
                "Classify this document excerpt into exactly one category: "
                "rate_card, contract, sop, invoice, data_log, or general. "
                "data_log means a tabular register or report of many similar "
                "records (e.g. fleet utilization logs, incident logs, delivery logs) "
                "rather than prose or a single structured document. "
                "Return only the category name, nothing else."
            ),
            user_message=sample_text[:3000],
            temperature=0,
        ).strip().lower()

        return result if result in DOCUMENT_TYPES else None
    except Exception:
        return None