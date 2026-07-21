import uuid

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Citation,
    DeveloperInfo,
    DocumentAnalysis,
)
from app.services.chat_service import handle_chat_message
from app.services.memory_service import get_recent_history

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post("", response_model=ChatResponse)
def send_message(request: ChatRequest):

    try:
        result = handle_chat_message(
            session_id=request.session_id,
            message=request.message,
            developer_mode=request.developer_mode,
            hybrid_search=request.hybrid_search,
            doc_id=request.doc_id,
            document_type=request.document_type,
        )

        return ChatResponse(
            answer=result["answer"],
            citations=[Citation(**c) for c in result["citations"]],
            confidence=result["confidence"],
            document_analysis=[
                DocumentAnalysis(**doc)
                for doc in result["document_analysis"]
            ],
            developer=(
                DeveloperInfo(**result["developer"])
                if result.get("developer")
                else None
            ),
            session_id=result["session_id"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process message: {e}",
        )


@router.post("/new")
def new_session():
    return {
        "session_id": str(uuid.uuid4())
    }


@router.get(
    "/{session_id}/history",
    response_model=ChatHistoryResponse,
)
def get_history(session_id: str):

    history = get_recent_history(
        session_id=session_id,
        limit=50,
    )

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            ChatMessage(**message)
            for message in history
        ],
    )