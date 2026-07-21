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
    document_type: str | None = None
    hybrid_search: bool = True


@router.post("/retrieve")
def debug_retrieve(request: DebugQuery):

    chunks = retrieve_chunks(
        query=request.query,
        doc_id=request.doc_id,
        document_type=request.document_type,
        hybrid=request.hybrid_search,
    )

    return {
        "query": request.query,
        "document_type_filter": request.document_type,
        "retrieved": len(chunks),
        "results": [
            {
                "filename": chunk["filename"],
                "page": chunk["page"],
                "section": chunk["section"],
                "document_type": chunk["document_type"],
                "similarity": chunk["similarity"],
                "text_preview": chunk["text"][:200],
            }
            for chunk in chunks
        ],
    }