import os
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
    MatchText,
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION = "documents"
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


class DocumentIndexer:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL)
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in collections:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )

    def index_chapters(
        self,
        doc_id: str,
        doc_title: str,
        chapters: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """
        将文档的所有章节存储到 Qdrant

        主要工作流：
        1. 为每个章节创建 PointStruct，包含文档 ID、标题、章节号、内容、时间戳、类型
        2. 批量 upsert 到 documents 集合
        3. 返回索引的章节数
        """
        points = []
        for i, (ch, emb) in enumerate(zip(chapters, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "doc_id": doc_id,
                        "doc_title": doc_title,
                        "chapter": ch["chapter"],
                        "title": ch["title"],
                        "content": ch["content"],
                        "total_chapters": len(chapters),
                        "timestamp": time.time(),
                        "type": "chapter",
                    },
                )
            )
        self.client.upsert(collection_name=COLLECTION, points=points)
        return len(points)

    def get_chapter(self, doc_id: str, chapter_num: int) -> dict | None:
        """Get a specific chapter's content."""
        results = self.client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(
                        key="chapter", match=MatchValue(value=chapter_num)
                    ),
                ]
            ),
            limit=1,
            with_payload=True,
        )[0]
        if results:
            p = results[0].payload
            return {
                "chapter": p["chapter"],
                "title": p["title"],
                "content": p["content"],
            }
        return None

    def search_related(
        self, doc_id: str, exclude_chapter: int, embedding: list[float], top_k: int = 6
    ) -> list[dict]:
        """Search semantically related chapters (excluding the specified one)."""
        results = self.client.query_points(
            collection_name=COLLECTION,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="type", match=MatchValue(value="chapter")),
                ]
            ),
            limit=top_k + 1,  # +1 because we'll filter out one
        )
        related = []
        for p in results.points:
            if p.payload["chapter"] == exclude_chapter:
                continue
            related.append(
                {
                    "chapter": p.payload["chapter"],
                    "title": p.payload["title"],
                    "content": p.payload["content"],
                    "score": p.score,
                }
            )
            if len(related) >= top_k:
                break
        return related

    def search_all(
        self, doc_id: str, embedding: list[float], top_k: int = 8
    ) -> list[dict]:
        """
        搜索文档中所有语义相关的段落

        主要工作流：
        1. 在 documents 集合中搜索指定文档 ID 且类型为 chapter 的点
        2. 按向量相似度排序
        3. 返回最多 top_k 条结果，包含章节号、标题、内容、相似度分数
        """
        results = self.client.query_points(
            collection_name=COLLECTION,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="type", match=MatchValue(value="chapter")),
                ]
            ),
            limit=top_k,
        )
        return [
            {
                "chapter": p.payload["chapter"],
                "title": p.payload["title"],
                "content": p.payload["content"],
                "score": p.score,
            }
            for p in results.points
        ]

    def list_documents(self) -> list[dict]:
        """List all indexed documents with chunk counts."""
        results = self.client.scroll(
            collection_name=COLLECTION,
            limit=500,
            with_payload=True,
        )[0]
        counts = {}
        seen_order = []
        for p in results:
            pid = p.payload["doc_id"]
            if pid not in counts:
                counts[pid] = {"id": pid, "title": p.payload["doc_title"], "count": 0}
                seen_order.append(pid)
            counts[pid]["count"] += 1
        return [counts[pid] for pid in seen_order]

    def delete_document(self, doc_id: str) -> bool:
        """Delete all chapters of a document."""
        self.client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        return True
