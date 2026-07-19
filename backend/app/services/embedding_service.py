import os
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastembed import TextEmbedding

from app.core.config import settings

_embedder = TextEmbedding(model_name=settings.embedding_model)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunks for storage. Use for ingestion, never for queries."""
    if not texts:
        return []
    return [e.tolist() for e in _embedder.embed(texts)]


def embed_query(query: str) -> list[float]:
    """Embed a search query. Uses BGE's asymmetric query prefix internally."""
    return next(_embedder.query_embed(query)).tolist()