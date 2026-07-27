import gc

import chromadb
from chromadb.config import Settings as ChromaSettings
from rank_bm25 import BM25Okapi

from app.core.config import settings


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self.collection = self.client.get_or_create_collection(
            name="opspilot_chunks",
            metadata={
                "hnsw:space": "cosine",
                # Leaner index graph than Chroma's defaults (16/200) --
                # less RAM per vector at a small recall cost.
                "hnsw:M": 16,
                "hnsw:construction_ef": 100,
            },
        )

        self._bm25 = None
        # Only ids + metadata are kept resident for BM25 bookkeeping --
        # chunk text is fetched from Chroma on demand for the handful of
        # BM25-only hits that need it per query, not cached a second time.
        self._ids: list[str] = []
        self._metadatas: list[dict] = []
        self._bm25_dirty = True

    def add_chunks(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ):
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        self._bm25_dirty = True

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        doc_id: str | None = None,
        document_type: str | None = None,
    ):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=_build_where(doc_id, document_type),
        )

    def hybrid_query(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        doc_id: str | None = None,
        document_type: str | None = None,
    ):
        self._ensure_bm25()

        dense = self.query(
            query_embedding=query_embedding,
            top_k=top_k * 2,
            doc_id=doc_id,
            document_type=document_type,
        )

        if not self._bm25:
            return dense

        bm25_scores = self._bm25.get_scores(query.lower().split())

        bm25_rank = sorted(
            enumerate(bm25_scores),
            key=lambda x: x[1],
            reverse=True,
        )

        fused = {}

        for rank, (doc, meta, dist) in enumerate(
            zip(
                dense["documents"][0],
                dense["metadatas"][0],
                dense["distances"][0],
            ),
            start=1,
        ):
            key = (meta["doc_id"], meta["chunk_id"])

            fused[key] = {
                "rrf": 1 / (60 + rank),
                "document": doc,
                "metadata": meta,
                "distance": dist,
            }

        bm25_added = 0

        for idx, _ in bm25_rank:
            meta = self._metadatas[idx]

            if doc_id and meta["doc_id"] != doc_id:
                continue

            if document_type and meta.get("document_type") != document_type:
                continue

            bm25_added += 1
            key = (meta["doc_id"], meta["chunk_id"])

            if key not in fused:
                # Only fetch text for chunks BM25 found that dense search
                # didn't already return -- a handful of targeted lookups
                # per query, not a resident copy of the whole corpus.
                fetched = self.collection.get(
                    ids=[self._ids[idx]],
                    include=["documents"],
                )
                text = fetched["documents"][0] if fetched["documents"] else ""

                fused[key] = {
                    "rrf": 0,
                    "document": text,
                    "metadata": meta,
                    "distance": 1.0,
                }

            fused[key]["rrf"] += 1 / (60 + bm25_added)

            if bm25_added >= top_k * 2:
                break

        ranked = sorted(
            fused.values(),
            key=lambda x: x["rrf"],
            reverse=True,
        )[:top_k]

        return {
            "documents": [[r["document"] for r in ranked]],
            "metadatas": [[r["metadata"] for r in ranked]],
            "distances": [[r["distance"] for r in ranked]],
        }

    def _ensure_bm25(self):
        if self._bm25_dirty:
            self._rebuild_bm25()
            self._bm25_dirty = False

    def _rebuild_bm25(self):
        data = self.collection.get(
            include=["documents", "metadatas"]
        )

        documents = data.get("documents", [])
        metadatas = data.get("metadatas", [])
        ids = data.get("ids", [])

        self._ids = ids
        self._metadatas = metadatas

        self._bm25 = (
            BM25Okapi([doc.lower().split() for doc in documents])
            if documents
            else None
        )

        # BM25Okapi retains word-frequency stats internally, not the raw
        # text -- no reason to keep this list resident afterward.
        del documents
        gc.collect()

    def delete_document(self, doc_id: str):
        self.collection.delete(where={"doc_id": doc_id})
        self._bm25_dirty = True

    def list_documents(self) -> list[dict]:
        data = self.collection.get(include=["metadatas"])

        documents = {}

        for meta in data.get("metadatas", []):

            doc = documents.setdefault(
                meta["doc_id"],
                {
                    "doc_id": meta["doc_id"],
                    "filename": meta["filename"],
                    "page_count": meta.get("page_count", 0),
                    "document_type": meta.get("document_type", "general"),
                    "chunk_count": 0,
                },
            )

            doc["chunk_count"] += 1

        return list(documents.values())


def _build_where(doc_id: str | None, document_type: str | None):
    conditions = []
    if doc_id:
        conditions.append({"doc_id": doc_id})
    if document_type:
        conditions.append({"document_type": document_type})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


vector_store = VectorStore()
