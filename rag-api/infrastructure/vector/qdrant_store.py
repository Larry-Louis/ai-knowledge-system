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
from infrastructure.config.config import Config


GLOBAL_SESSION = "__global__"


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(url=Config.QDRANT_URL)
        self._ensure_indexes()
        self.collection = Config.QDRANT_MEMORY_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        import time
        for attempt in range(30):
            try:
                collections = [c.name for c in self.client.get_collections().collections]
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)
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
        """
        [S0-10] [S0-11] 同步写入 Qdrant：将记忆单元存储到向量数据库

        主要工作流：
        1. 生成唯一 point_id
        2. 创建 PointStruct 包含会话 ID、角色、层、内容、时间戳、类型
        3. 调用 Qdrant upsert 写入集合
        4. 返回 point_id
        """
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
        """
        [S0-4] 三重记忆检索 - 当前会话记忆

        主要工作流：
        1. 在 Qdrant 中搜索指定会话 ID 且类型为 memory 的点
        2. 按向量相似度排序
        3. 返回最多 top_k 条记忆，包含内容、角色、相似度分数、时间戳
        """
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
        """
        [S0-4] 三重记忆检索 - 全局跨会话记忆

        主要工作流：
        1. 在 Qdrant 中搜索所有会话中类型为 memory 的点
        2. 如果指定了 layers，则按层过滤
        3. 对 core 层的记忆应用 1.05 倍权重提升
        4. 返回最多 top_k 条记忆，包含内容、角色、会话 ID、层、相似度分数
        """
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
        CORE_BOOST = 1.05
        return [
            {
                "content": p.payload["content"],
                "role": p.payload.get("role", "user"),
                "session_id": p.payload.get("session_id", ""),
                "layer": p.payload.get("layer", ""),
                "score": p.score * CORE_BOOST if p.payload.get("layer") == "core" else p.score,
            }
            for p in results.points
        ]

    def get_recent_global_memories(
        self, exclude_session: str = "", limit: int = 6, layers: list[str] | None = None
    ) -> list[dict]:
        """
        [S0-4] 三重记忆检索 - 新会话预热记忆

        主要工作流：
        1. 按时间戳降序滚动所有会话中类型为 memory 的点
        2. 排除指定会话 ID 的记忆
        3. 去重（按内容前 100 字符）
        4. 返回最多 limit 条最近记忆，用于新会话预热
        """
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
        """
        [S0-6] 文档检索：搜索上传文档中的相关内容

        主要工作流：
        1. 在 documents 集合中搜索类型为 chapter 的点
        2. 如果指定了 doc_ids，则只搜索这些文档
        3. 过滤掉相似度低于 0.65 的结果
        4. 返回最多 top_k 条文档片段，包含内容、章节号、标题、文档标题、相似度分数
        """
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
        """
        [S0-6] 摘要检索：获取最新的世界观摘要

        主要工作流：
        1. 在记忆集合中搜索类型为 summary 的点
        2. 返回最新一条摘要的内容
        3. 如果没有摘要则返回 None
        """
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
        """
        [S0-13] 保存世界观摘要

        主要工作流：
        1. 删除所有旧的摘要记录
        2. 将新摘要作为类型为 summary 的记忆写入全局会话
        """
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

    def _ensure_indexes(self):
        try:
            from qdrant_client import models
            self.client.create_payload_index(
                collection_name=Config.QDRANT_MEMORY_COLLECTION,
                field_name='timestamp',
                field_schema=models.PayloadSchemaType.INTEGER
            )
        except Exception:
            pass
