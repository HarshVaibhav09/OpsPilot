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
            metadata={"hnsw:space": "cosine"},
        )

        self._bm25 = None
        # Only ids + metadata are kept resident for BM25 bookkeeping --
        # NOT the full chunk text a second time. Previously this cached
        # every chunk's full text ("self._documents") on top of what's
        # already stored in Chroma, meaning the whole corpus's text
        # existed resident in memory twice (three times counting
        # BM25Okapi's own internal tokenized stats), and that cache
        # grew with every document ever ingested -- a compounding
        # memory cost as the corpus grows. Chunk text is now fetched
        # from Chroma on demand, only for the handful of BM25-only
        # hits that need it per query.
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
    ):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"doc_id": doc_id} if doc_id else None,
        )

    def hybrid_query(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        doc_id: str | None = None,
    ):
        self._ensure_bm25()

        dense = self.query(
            query_embedding=query_embedding,
            top_k=top_k * 2,
            doc_id=doc_id,
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

            bm25_added += 1
            key = (meta["doc_id"], meta["chunk_id"])

            if key not in fused:
                # Only fetch text for chunks BM25 found that dense
                # search didn't already return -- this is a handful of
                # small, targeted lookups per query, not a resident
                # copy of the whole corpus.
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

        # `documents` (the full corpus's raw text) was only needed to
        # build the BM25 index above -- BM25Okapi retains word-frequency
        # statistics internally, not the raw text itself, so there's no
        # reason to keep this list resident afterward.
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


vector_store = VectorStore()