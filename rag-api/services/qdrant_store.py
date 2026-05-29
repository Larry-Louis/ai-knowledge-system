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

    def get_summary(self, session_id: str) -> str | None:
        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="session_id", match=MatchValue(value=session_id)
                    ),
                    FieldCondition(key="type", match=MatchValue(value="summary")),
                ]
            ),
            limit=1,
            with_payload=True,
        )[0]
        return results[0].payload.get("content") if results else None

    def save_summary(self, session_id: str, summary: str, embedding: list[float]):
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id", match=MatchValue(value=session_id)
                        ),
                        FieldCondition(
                            key="type", match=MatchValue(value="summary")
                        ),
                    ]
                )
            ),
        )
        self.upsert_memory(
            session_id, "system", summary, embedding, point_type="summary"
        )
