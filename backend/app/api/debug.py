from fastapi import APIRouter
from pydantic import BaseModel

from app.services.retrieval_service import retrieve_chunks

router = APIRouter(
    prefix="/debug",
    tags=["debug"],
)


class DebugQuery(BaseModel):
    query: str
    doc_id: str | None = None
    hybrid_search: bool = True


@router.post("/retrieve")
def debug_retrieve(request: DebugQuery):

    chunks = retrieve_chunks(
        query=request.query,
        doc_id=request.doc_id,
        hybrid=request.hybrid_search,
    )

    return {
        "query": request.query,
        "retrieved": len(chunks),
        "results": [
            {
                "filename": chunk["filename"],
                "page": chunk["page"],
                "section": chunk["section"],
                "similarity": chunk["similarity"],
                "text_preview": chunk["text"][:200],
            }
            for chunk in chunks
        ],
    }