import os

if os.getenv("HF_HUB_OFFLINE") == "1":
    os.environ["HF_HUB_OFFLINE"] = "1"

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # LLM
    llm_provider: str = "groq"
    llm_api_key: str
    llm_model: str = "llama-3.3-70b-versatile"

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Chunking
    chunk_size: int = 700
    chunk_overlap: int = 120

    # Retrieval
    top_k_retrieval: int = 8
    top_k_final: int = 5

    # Ingestion limits
    max_pages: int = 60

    # Storage
    chroma_persist_dir: str = "./data/chroma"
    session_db_path: str = "./data/sessions.db"

    # Frontend
    cors_origins: str = "http://localhost:5173"


settings = Settings()