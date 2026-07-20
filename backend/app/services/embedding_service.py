import gc
import os

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastembed import TextEmbedding

from app.core.config import settings

# Load the AI model only when it's actually needed, not when the app starts.
# Before, the model loaded immediately on startup and stayed in RAM forever,
# even if no one uploaded anything. That wastes memory on a small server.
_embedder: TextEmbedding | None = None

DEFAULT_EMBED_BATCH_SIZE = 16


def _get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name=settings.embedding_model)
    return _embedder


def embed_documents(
    texts: list[str],
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
) -> list[list[float]]:
    """Embed chunks for storage. Use for ingestion, never for queries.

    Process texts in small batches instead of all at once. Embedding
    everything in one go uses memory proportional to the whole document,
    which can crash a low-RAM server. Small batches keep memory usage
    low and steady, no matter how big the document is.
    """
    if not texts:
        return []

    embedder = _get_embedder()
    results: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        results.extend(e.tolist() for e in embedder.embed(batch))

    return results


def embed_query(query: str) -> list[float]:
    """Embed a search query. Uses BGE's asymmetric query prefix internally."""
    return next(_get_embedder().query_embed(query)).tolist()


def release_embedder_memory() -> None:
    """Free the loaded model from memory. Not called automatically —
    use it if you want to reclaim RAM during idle periods (model will
    just reload next time it's needed)."""
    global _embedder
    _embedder = None
    gc.collect()