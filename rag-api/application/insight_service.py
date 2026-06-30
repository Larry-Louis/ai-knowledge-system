from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infrastructure.embedding.embedding import EmbeddingService
from infrastructure.vector.qdrant_store import QdrantStore


@dataclass
class InsightRecord:
    insight_id: str
    user_id: str
    category: str
    content: str
    confidence: float
    evidence_refs: list[str]
    status: str = "active"
    version: int = 1


class InsightService:
    """Phase2 Week1: Insight 存储与读取最小闭环服务。"""

    def __init__(self, store: QdrantStore | None = None):
        self.store = store or QdrantStore()

    def create_insight(
        self,
        user_id: str,
        category: str,
        content: str,
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
        status: str = "active",
        version: int = 1,
    ) -> InsightRecord:
        embedding = EmbeddingService.embed(content)
        insight_id = self.store.upsert_insight(
            user_id=user_id,
            category=category,
            content=content,
            embedding=embedding,
            confidence=confidence,
            evidence_refs=evidence_refs,
            status=status,
            version=version,
        )
        return InsightRecord(
            insight_id=insight_id,
            user_id=user_id,
            category=category,
            content=content,
            confidence=max(0.0, min(1.0, confidence)),
            evidence_refs=evidence_refs or [],
            status=status,
            version=version,
        )

    def search_insights(
        self,
        user_id: str,
        query_text: str,
        top_k: int = 6,
        categories: list[str] | None = None,
        only_active: bool = True,
    ) -> list[dict[str, Any]]:
        embedding = EmbeddingService.embed(query_text)
        return self.store.search_insights(
            embedding=embedding,
            user_id=user_id,
            top_k=top_k,
            categories=categories,
            only_active=only_active,
        )

    def build_user_profile_snapshot(self, user_id: str, limit: int = 20) -> dict[str, Any]:
        """将最近 Insight 组装为 prompt 可用的用户画像快照。"""
        recent = self.store.get_recent_insights(user_id=user_id, limit=limit, only_active=True)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in recent:
            grouped.setdefault(item.get("category", "general"), []).append(item)

        return {
            "user_id": user_id,
            "total_insights": len(recent),
            "categories": {
                category: [
                    {
                        "content": x.get("content", ""),
                        "confidence": x.get("confidence", 0.0),
                        "version": x.get("version", 1),
                        "evidence_refs": x.get("evidence_refs", []),
                    }
                    for x in values
                ]
                for category, values in grouped.items()
            },
        }


__all__ = ["InsightService", "InsightRecord"]
