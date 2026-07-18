from typing import Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    doc_id: str
    filename: str
    page_count: int
    chunk_count: int
    has_conflicts: bool = False


class UploadResponse(BaseModel):
    documents: list[DocumentMetadata]


class Citation(BaseModel):
    filename: str
    page: int
    section: str
    snippet: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    developer_mode: bool = False
    hybrid_search: bool = True
    doc_id: Optional[str] = None


class Conflict(BaseModel):
    topic: str
    page_a: int
    statement_a: str
    page_b: int
    statement_b: str
    severity: str


class ContradictionAnalysis(BaseModel):
    has_conflict: bool
    conflicts: list[Conflict] = Field(default_factory=list)


class DocumentAnalysis(BaseModel):
    filename: str
    contradictions: ContradictionAnalysis
    query_suggestions: list[str] = Field(default_factory=list)


class DeveloperInfo(BaseModel):
    rewritten_query: str
    avg_similarity: float
    context_length: int
    hybrid_search: bool
    retrieved_chunks: list[dict]


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]

    confidence: float

    document_analysis: list[DocumentAnalysis] = Field(default_factory=list)

    developer: Optional[DeveloperInfo] = None

    session_id: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]