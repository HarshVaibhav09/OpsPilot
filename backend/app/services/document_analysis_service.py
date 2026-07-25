import json

# from sympy import false

from app.core.llm_client import llm_client

_analysis_store: dict[str, dict] = {}

SYSTEM_PROMPT = """
You are OpsPilot, an elite Enterprise Document Intelligence Engine specializing in deep document understanding, consistency analysis, semantic reasoning, and information extraction.

Your task is to analyze ONE document for internal consistency and generate useful follow-up questions using ONLY the supplied document content.

========================
PRIMARY OBJECTIVES
========================

1. Detect every verifiable internal contradiction or inconsistency.
2. Generate intelligent follow-up questions a user is likely to ask.

Your analysis must prioritize factual correctness, completeness, consistency, and precision over brevity.

Never fabricate information.

Never infer facts that are not explicitly supported by the supplied document.

If evidence is insufficient, state that the evidence is insufficient.

========================
CONTRADICTION ANALYSIS
========================

Perform a full-document consistency check.

Treat the document as a single source of truth.

Compare ALL available sections against each other.

Search for inconsistencies involving (but not limited to):
• Company names
• Person names
• Dates
• Addresses
• Phone numbers
• Email IDs
• Organizations
• Numerical values
• IDs
• Version numbers
• Currency values
• Locations
• Product names
• Quantities
• Timelines
• Duplicated information with conflicting values
• Repeated sections containing different facts


Examples of contradictions include:

Different addresses.

Different phone numbers.

Different email IDs.

Conflicting totals.

Conflicting monetary values.

Conflicting incident dates.

Conflicting IDs.

If multiple values legitimately coexist without conflict,
DO NOT classify them as contradictions.

Only report genuine inconsistencies.

Each contradiction must contain:

topic

description

page_a

statement_a

page_b

statement_b

severity

Severity definitions:

LOW
Minor inconsistency that does not change document meaning.

MEDIUM
Inconsistency that could confuse readers.

HIGH
Critical contradiction affecting identity, legality, ownership, financial values, dates, or business decisions.

========================
QUERY SUGGESTIONS
========================

Generate 2 intelligent questions a user is likely to ask after reading the document whose answers are already available within the document.

Suggestions should:

be natural

be useful

cover different aspects

not repeat each other

Examples:

"What is the incident date?"

"Which driver was involved?"

"Summarize the compliance violations."

"List all safety incidents."

========================
OUTPUT FORMAT
========================

Return ONLY valid JSON.

No markdown.

No explanations.

Schema:

{
  "contradictions": {
    "has_conflict": False,
    "conflicts": [
      {
        "topic": "",
        "description": "",
        "page_a": 0,
        "statement_a": "",
        "page_b": 0,
        "statement_b": "",
        "severity": "Low or medium or high"
      }
    ]
  },
  "query_suggestions": [
    ""
  ]
}

========================
STRICT RULES
========================

1. Use ONLY supplied document content.

2. Never hallucinate.

3. Never invent pages.

4. Never invent contradictions.

5. Never omit obvious contradictions.

6. Report every contradiction supported by evidence.

7. If no contradiction exists:

{
  "has_conflict": false,
  "conflicts": []
}

8. Return syntactically valid JSON.

9. Do not output any text outside JSON.

10. Be deterministic and internally consistent.
"""


MAX_ANALYSIS_CHUNKS = 100      # Tune according to your model context window


def analyze_document(
    doc_id: str,
    filename: str,
    chunks: list[dict],
) -> dict:

    # ---------- Cache ----------
    cached = _analysis_store.get(doc_id)
    if cached:
        return cached

    if not chunks:
        analysis = {
            "filename": filename,
            "contradictions": {
                "has_conflict": False,
                "conflicts": [],
            },
            "query_suggestions": [],
        }
        _analysis_store[doc_id] = analysis
        return analysis

    # ---------- Sort chunks ----------
    sorted_chunks = sorted(
        chunks,
        key=lambda c: (
            c["metadata"].get("page", 0),
            c["metadata"].get("chunk_id", 0),
        ),
    )

    # ---------- Select context ----------
    selected_chunks = sorted_chunks[:MAX_ANALYSIS_CHUNKS]

    total_pages = max(
        c["metadata"].get("page", 1)
        for c in sorted_chunks
    )

    context = (
        f"Filename: {filename}\n"
        f"Total Pages: {total_pages}\n"
        f"Total Chunks: {len(sorted_chunks)}\n\n"
        "Document:\n\n"
    )

    context += "\n\n".join(
        f"[Page {c['metadata'].get('page', 1)} | "
        f"{c['metadata'].get('section', 'General')}]\n"
        f"{c['text']}"
        for c in selected_chunks
    )

    response = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_message=context,
        temperature=0,
    )

    # ---------- Parse JSON ----------
    try:
        response = response.strip()

        if response.startswith("```"):
            response = (
                response.replace("```json", "")
                .replace("```", "")
                .strip()
            )

        analysis = json.loads(response)

    except Exception as e:

        print("Document analysis parsing failed:", e)
        print(response)

        analysis = {
            "contradictions": {
                "has_conflict": False,
                "conflicts": [],
            },
            "query_suggestions": [],
        }

    # ---------- Defensive validation ----------
    analysis.setdefault("query_suggestions", [])

    analysis.setdefault(
        "contradictions",
        {
            "has_conflict": False,
            "conflicts": [],
        },
    )

    analysis["filename"] = filename

    _analysis_store[doc_id] = analysis

    return analysis


def get_document_analysis(doc_id: str) -> dict:

    return _analysis_store.get(
        doc_id,
        {
            "filename": "",
            "contradictions": {
                "has_conflict": False,
                "conflicts": [],
            },
            "query_suggestions": [],
        },
    )


def clear_document(doc_id: str):
    _analysis_store.pop(doc_id, None)