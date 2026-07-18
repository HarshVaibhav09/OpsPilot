from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, debug, documents
from app.core.config import settings

app = FastAPI(
    title="OpsPilot API",
    description="Enterprise RAG system for querying and analyzing operational documents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(debug.router)


@app.get("/")
def root():
    return {
        "service": "OpsPilot API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
    }