from __future__ import annotations

import uuid
from typing import Any, Callable

from .chunking import compute_similarity
from .embeddings import _mock_embed
from .models import Document


class EmbeddingStore:
    """
    A vector store for text chunks.

    Tries to use ChromaDB if available; falls back to an in-memory store.
    The embedding_fn parameter allows injection of mock embeddings for tests.
    """

    def __init__(
        self,
        collection_name: str = "documents",
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        self._embedding_fn = embedding_fn or _mock_embed
        self._collection_name = collection_name
        self._use_chroma = False
        self._store: list[dict[str, Any]] = []
        self._collection = None
        self._next_index = 0

        try:
            import chromadb

            self._client = chromadb.Client()
            chroma_collection_name = f"{collection_name[:40]}-{uuid.uuid4().hex[:8]}"
            self._collection = self._client.get_or_create_collection(
                name=chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_chroma = True
        except Exception:
            self._use_chroma = False
            self._collection = None

    def _make_record(self, doc: Document) -> dict[str, Any]:
        metadata = dict(doc.metadata or {})
        metadata.setdefault("doc_id", doc.id)
        record_id = f"{doc.id}-{self._next_index}"
        self._next_index += 1
        return {
            "id": record_id,
            "content": doc.content,
            "metadata": metadata,
            "embedding": self._embedding_fn(doc.content),
        }

    def _search_records(self, query: str, records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0 or not records:
            return []

        query_embedding = self._embedding_fn(query)
        scored_results: list[dict[str, Any]] = []

        for record in records:
            score = compute_similarity(query_embedding, record["embedding"])
            scored_results.append(
                {
                    "id": record["id"],
                    "content": record["content"],
                    "metadata": dict(record["metadata"]),
                    "score": score,
                }
            )

        scored_results.sort(key=lambda item: item["score"], reverse=True)
        return scored_results[:top_k]

    def _search_chroma(
        self,
        query: str,
        top_k: int,
        metadata_filter: dict | None = None,
    ) -> list[dict[str, Any]]:
        if top_k <= 0 or self._collection is None or self._collection.count() == 0:
            return []

        query_embedding = self._embedding_fn(query)
        raw_results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
            where=metadata_filter,
            include=["documents", "metadatas", "distances"],
        )

        ids = raw_results.get("ids", [[]])[0]
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        results: list[dict[str, Any]] = []
        for record_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
            results.append(
                {
                    "id": record_id,
                    "content": content,
                    "metadata": dict(metadata or {}),
                    "score": 1.0 - float(distance),
                }
            )

        return results

    def add_documents(self, docs: list[Document]) -> None:
        """
        Embed each document's content and store it.

        For ChromaDB: use collection.add(ids=[...], documents=[...], embeddings=[...])
        For in-memory: append dicts to self._store
        """
        records = [self._make_record(doc) for doc in docs]
        if not records:
            return

        self._store.extend(records)

        if self._use_chroma and self._collection is not None:
            try:
                self._collection.add(
                    ids=[record["id"] for record in records],
                    documents=[record["content"] for record in records],
                    embeddings=[record["embedding"] for record in records],
                    metadatas=[record["metadata"] for record in records],
                )
            except Exception:
                self._use_chroma = False

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Find the top_k most similar documents to query.

        For in-memory: compute dot product of query embedding vs all stored embeddings.
        """
        if self._use_chroma and self._collection is not None:
            try:
                return self._search_chroma(query, top_k=top_k)
            except Exception:
                self._use_chroma = False

        return self._search_records(query, self._store, top_k)

    def get_collection_size(self) -> int:
        """Return the total number of stored chunks."""
        if self._use_chroma and self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                self._use_chroma = False

        return len(self._store)

    def search_with_filter(self, query: str, top_k: int = 3, metadata_filter: dict = None) -> list[dict]:
        """
        Search with optional metadata pre-filtering.

        First filter stored chunks by metadata_filter, then run similarity search.
        """
        if not metadata_filter:
            return self.search(query, top_k=top_k)

        if self._use_chroma and self._collection is not None:
            try:
                return self._search_chroma(query, top_k=top_k, metadata_filter=metadata_filter)
            except Exception:
                self._use_chroma = False

        filtered_records = [
            record
            for record in self._store
            if all(record["metadata"].get(key) == value for key, value in metadata_filter.items())
        ]
        return self._search_records(query, filtered_records, top_k)

    def delete_document(self, doc_id: str) -> bool:
        """
        Remove all chunks belonging to a document.

        Returns True if any chunks were removed, False otherwise.
        """
        if self._use_chroma and self._collection is not None:
            try:
                matches = self._collection.get(where={"doc_id": doc_id})
                ids_to_delete = matches.get("ids", [])
                if not ids_to_delete:
                    return False

                self._collection.delete(ids=ids_to_delete)
                self._store = [record for record in self._store if record["id"] not in ids_to_delete]
                return True
            except Exception:
                self._use_chroma = False

        ids_to_delete = [
            record["id"]
            for record in self._store
            if record["metadata"].get("doc_id") == doc_id
        ]
        if not ids_to_delete:
            return False

        self._store = [record for record in self._store if record["id"] not in ids_to_delete]

        if self._use_chroma and self._collection is not None:
            try:
                self._collection.delete(ids=ids_to_delete)
            except Exception:
                self._use_chroma = False

        return True
