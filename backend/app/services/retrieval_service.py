from app.core.config import settings
from app.db.vector_store import vector_store
from app.services.ingestion_service import _embedder


def retrieve_chunks(
    query: str,
    doc_id: str | None = None,
    hybrid: bool = True,
) -> list[dict]:

    query_embedding = _embedder.encode(
        query,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).tolist()

    results = (
        vector_store.hybrid_query(
            query=query,
            query_embedding=query_embedding,
            top_k=settings.top_k_retrieval,
            doc_id=doc_id,
        )
        if hybrid
        else vector_store.query(
            query_embedding=query_embedding,
            top_k=settings.top_k_retrieval,
            doc_id=doc_id,
        )
    )

    candidates = _format_results(results)

    if not candidates:
        return []

    return candidates[: settings.top_k_final]


def _format_results(results: dict) -> list[dict]:

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {
            "doc_id": meta["doc_id"],
            "chunk_id": meta.get("chunk_id"),
            "filename": meta["filename"],
            "page": meta["page"],
            "section": meta.get("section", "General"),
            "content_type": meta.get("content_type", "text"),
            "text": text,
            "similarity": round(max(0.0, 1 - distance), 4),
        }
        for text, meta, distance in zip(documents, metadatas, distances)
    ]