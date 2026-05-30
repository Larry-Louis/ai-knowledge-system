import uuid
import time
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    FilterSelector,
)
from core.config import Config


GLOBAL_SESSION = "__global__"


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(url=Config.QDRANT_URL)
        self.collection = Config.QDRANT_MEMORY_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=Config.EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )

    def upsert_memory(
        self,
        session_id: str,
        role: str,
        content: str,
        embedding: list[float],
        point_type: str = "memory",
        layer: str = "general",
    ) -> str:
        point_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "session_id": session_id,
                        "role": role,
                        "layer": layer,
                        "content": content,
                        "timestamp": time.time(),
                        "type": point_type,
                    },
                )
            ],
        )
        return point_id

    def search_memories(
        self, embedding: list[float], session_id: str, top_k: int = 8
    ) -> list[dict]:
        # Session-specific memories
        results = self.client.query_points(
            collection_name=self.collection,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="session_id", match=MatchValue(value=session_id)
                    ),
                    FieldCondition(key="type", match=MatchValue(value="memory")),
                ]
            ),
            limit=top_k,
        )
        return [
            {
                "content": p.payload["content"],
                "role": p.payload.get("role", "user"),
                "score": p.score,
                "timestamp": p.payload.get("timestamp", 0),
            }
            for p in results.points
        ]

    def search_global_memories(
        self, embedding: list[float], top_k: int = 6, layers: list[str] | None = None
    ) -> list[dict]:
        """Search across all sessions for globally relevant memories, filtered by layers."""
        conditions = [FieldCondition(key="type", match=MatchValue(value="memory"))]
        if layers:
            from qdrant_client.models import MatchAny
            conditions.append(FieldCondition(key="layer", match=MatchAny(any=layers)))

        results = self.client.query_points(
            collection_name=self.collection,
            query=embedding,
            query_filter=Filter(must=conditions),
            limit=top_k,
        )
        return [
            {
                "content": p.payload["content"],
                "role": p.payload.get("role", "user"),
                "session_id": p.payload.get("session_id", ""),
                "score": p.score,
            }
            for p in results.points
        ]

    def get_recent_global_memories(
        self, exclude_session: str = "", limit: int = 6, layers: list[str] | None = None
    ) -> list[dict]:
        """Get the most recent memories across all sessions (by timestamp)."""
        conditions = [FieldCondition(key="type", match=MatchValue(value="memory"))]
        if layers:
            from qdrant_client.models import MatchAny
            conditions.append(FieldCondition(key="layer", match=MatchAny(any=layers)))
        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(must=conditions),
            limit=limit * 3,
            with_payload=True,
            order_by={"key": "timestamp", "direction": "desc"},
        )[0]
        seen = set()
        result = []
        for p in results:
            sid = p.payload.get("session_id", "")
            if sid == exclude_session:
                continue
            content = p.payload.get("content", "")
            key = content[:100]
            if key not in seen:
                seen.add(key)
                result.append({
                    "content": content,
                    "role": p.payload.get("role", "user"),
                    "session_id": sid,
                    "timestamp": p.payload.get("timestamp", 0),
                })
            if len(result) >= limit:
                break
        return result

    DOCUMENTS_COLLECTION = "documents"

    DOC_SCORE_THRESHOLD = 0.65

    def search_documents(self, embedding: list[float], top_k: int = 4, doc_ids: list[str] | None = None) -> list[dict]:
        """Search uploaded documents for relevant content. If doc_ids provided, only search those documents."""
        conditions = [FieldCondition(key="type", match=MatchValue(value="chapter"))]
        if doc_ids:
            from qdrant_client.models import MatchAny
            conditions.append(FieldCondition(key="doc_id", match=MatchAny(any=doc_ids)))

        results = self.client.query_points(
            collection_name=self.DOCUMENTS_COLLECTION,
            query=embedding,
            query_filter=Filter(must=conditions),
            limit=top_k,
        )
        return [
            {
                "content": p.payload["content"],
                "chapter": p.payload.get("chapter", ""),
                "title": p.payload.get("title", ""),
                "doc_title": p.payload.get("doc_title", ""),
                "score": p.score,
            }
            for p in results.points
            if p.score >= self.DOC_SCORE_THRESHOLD
        ]

    def get_summary(self) -> str | None:
        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="type", match=MatchValue(value="summary"))]
            ),
            limit=1,
            with_payload=True,
        )[0]
        return results[0].payload.get("content") if results else None

    def save_summary(self, summary: str, embedding: list[float]):
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="type", match=MatchValue(value="summary"))]
                )
            ),
        )
        self.upsert_memory(
            GLOBAL_SESSION, "system", summary, embedding, point_type="summary"
        )
