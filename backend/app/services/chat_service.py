from app.core.llm_client import llm_client
from app.core.prompts import (
    RAG_SYSTEM_PROMPT,
    QUERY_REWRITE_PROMPT,
)

from app.services.analytics_service import analytics_service
from app.services.document_analysis_service import get_document_analysis
from app.services.memory_service import (
    get_recent_history,
    save_turn,
)
from app.services.retrieval_service import retrieve_chunks


def handle_chat_message(
    session_id: str,
    message: str,
    developer_mode: bool = False,
    hybrid_search: bool = True,
    doc_id: str | None = None,
    document_type: str | None = None,
) -> dict:

    history = get_recent_history(session_id)
    standalone_query = _contextualize_query(message, history)

    chunks = retrieve_chunks(
        query=standalone_query,
        doc_id=doc_id,
        document_type=document_type,
        hybrid=hybrid_search,
    )

    if not chunks:
        answer = "I couldn't find enough information in the uploaded documents to answer your question."

        save_turn(
            session_id=session_id,
            user_message=message,
            assistant_message=answer,
            standalone_query=standalone_query,
            confidence=0.0,
        )

        return {
            "answer": answer,
            "citations": [],
            "confidence": 0.0,
            "document_analysis": [],
            "developer": {} if developer_mode else None,
            "session_id": session_id,
        }

    context = _format_context(chunks)

    answer = llm_client.generate(
        system_prompt=RAG_SYSTEM_PROMPT.format(
            context=context,
            history=_format_history(history),
        ),
        user_message=message,
    )

    confidence = _calculate_confidence(chunks)

    analytics_service.log_query(
        session_id=session_id,
        query=message,
        retrieved=len(chunks),
        confidence=confidence,
    )

    citations = _build_citations(chunks)

    analyses = [
        get_document_analysis(doc)
        for doc in {c["doc_id"] for c in chunks}
    ]

    document_analysis = [
        {
            "filename": analysis["filename"],
            "contradictions": analysis["contradictions"],
            "query_suggestions": analysis["query_suggestions"],
        }
        for analysis in analyses
    ]

    save_turn(
        session_id=session_id,
        user_message=message,
        assistant_message=answer,
        standalone_query=standalone_query,
        confidence=confidence,
    )

    response = {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "document_analysis": document_analysis,
        "session_id": session_id,
    }

    if developer_mode:
        response["developer"] = {
            "rewritten_query": standalone_query,
            "avg_similarity": round(
                sum(c["similarity"] for c in chunks) / len(chunks),
                3,
            ),
            "context_length": len(context),
            "hybrid_search": hybrid_search,
            "document_type_filter": document_type,
            "retrieved_chunks": chunks,
        }
    return response


def _calculate_confidence(
    chunks: list[dict],
) -> float:

    similarity = sum(
        c["similarity"] for c in chunks
    ) / len(chunks)

    return round(min(similarity, 1.0), 2)


def _contextualize_query(
    message: str,
    history: list[dict],
) -> str:

    if not history:
        return message

    return llm_client.generate(
        system_prompt="Rewrite the user's question into a standalone query.",
        user_message=QUERY_REWRITE_PROMPT.format(
            history=_format_history(history),
            question=message,
        ),
        temperature=0,
    ).strip()


def _format_context(
    chunks: list[dict],
) -> str:

    return "\n\n".join(
        f"[{c['filename']} | Page {c['page']} | {c['section']}]\n{c['text']}"
        for c in chunks
    )


def _format_history(history):

    if not history:
        return "No previous conversation."

    lines = ["Previous Conversation:\n"]

    for item in history:

        speaker = (
            "User"
            if item["role"] == "user"
            else "Assistant"
        )

        if (
            speaker == "User"
            and item.get("standalone_query")
        ):

            lines.append(
                f"""User:
                Original Question: {item['content']}
                Resolved Question: {item['standalone_query']}
                """
            )

        else:

            lines.append(
                f"""{speaker}:
                {item['content']}
                """
            )

    return "\n".join(lines)


def _build_citations(
    chunks: list[dict],
) -> list[dict]:

    citations = []
    seen = set()

    for chunk in chunks:

        key = (
            chunk["filename"],
            chunk["page"],
            chunk["section"],
        )

        if key in seen:
            continue

        seen.add(key)

        citations.append(
            {
                "filename": chunk["filename"],
                "page": chunk["page"],
                "section": chunk["section"],
                "snippet": chunk["text"][:180],
            }
        )

    return citations