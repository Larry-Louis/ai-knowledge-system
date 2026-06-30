from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infrastructure.embedding.embedding import EmbeddingService
from infrastructure.vector.qdrant_store import QdrantStore
from domain.memory.math_utils import cosine_similarity


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

    DUPLICATE_SIMILARITY_THRESHOLD = 0.88
    CONFLICT_SIMILARITY_THRESHOLD = 0.62

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
        return self.resolve_and_create_insight(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            evidence_refs=evidence_refs,
            status=status,
            version=version,
        )

    def resolve_and_create_insight(
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
        existing = self.store.search_insights(
            embedding=embedding,
            user_id=user_id,
            top_k=5,
            categories=[category],
            only_active=True,
        )

        if existing:
            best = existing[0]
            best_score = float(best.get("score", 0.0))
            best_content = best.get("content", "")
            best_version = int(best.get("version", 1) or 1)
            merged_refs = list(dict.fromkeys((best.get("evidence_refs", []) or []) + (evidence_refs or [])))

            if best_score >= self.DUPLICATE_SIMILARITY_THRESHOLD:
                return self._update_existing_insight(
                    insight_id=best["insight_id"],
                    user_id=user_id,
                    category=category,
                    content=best_content or content,
                    confidence=max(confidence, float(best.get("confidence", 0.0))),
                    evidence_refs=merged_refs,
                    status="active",
                    version=best_version + 1,
                )

            if self._has_conflict(content, best_content):
                self._update_existing_insight(
                    insight_id=best["insight_id"],
                    user_id=user_id,
                    category=category,
                    content=best_content,
                    confidence=float(best.get("confidence", 0.0)),
                    evidence_refs=merged_refs,
                    status="conflicted",
                    version=best_version + 1,
                )
                version = max(version, best_version + 1)

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

    def _update_existing_insight(
        self,
        insight_id: str,
        user_id: str,
        category: str,
        content: str,
        confidence: float,
        evidence_refs: list[str],
        status: str,
        version: int,
    ) -> InsightRecord:
        embedding = EmbeddingService.embed(content)
        self.store.upsert_insight(
            insight_id=insight_id,
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
            evidence_refs=evidence_refs,
            status=status,
            version=version,
        )

    def _has_conflict(self, new_content: str, old_content: str) -> bool:
        new_lower = (new_content or "").lower()
        old_lower = (old_content or "").lower()
        if not new_lower or not old_lower:
            return False

        pairs = [
            ("我喜欢", "我不喜欢"),
            ("喜欢", "不喜欢"),
            ("准备", "不准备"),
            ("计划", "不计划"),
            ("一直", "不再"),
            ("长期", "短期"),
            ("支持", "反对"),
            ("希望", "不希望"),
        ]
        for positive, negative in pairs:
            if (positive in new_lower and negative in old_lower) or (negative in new_lower and positive in old_lower):
                return True

        # 当新旧洞察彼此向量相似度很低时，视为同类主题的潜在变化，但不强制冲突。
        similarity = cosine_similarity(EmbeddingService.embed(new_content), EmbeddingService.embed(old_content))
        return similarity < self.CONFLICT_SIMILARITY_THRESHOLD and any(marker in new_content for marker in ("我", "我们", "我的"))

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

    def list_insight_history(
        self,
        user_id: str,
        limit: int = 50,
        categories: list[str] | None = None,
        only_active: bool = False,
    ) -> dict[str, Any]:
        """返回洞察历史，默认包含 active/conflicted/deprecated 全部状态。"""
        items = self.store.get_recent_insights(
            user_id=user_id,
            limit=limit,
            categories=categories,
            only_active=only_active,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(item.get("category", "general"), []).append(
                {
                    "insight_id": item.get("insight_id", ""),
                    "content": item.get("content", ""),
                    "confidence": item.get("confidence", 0.0),
                    "status": item.get("status", "active"),
                    "version": item.get("version", 1),
                    "timestamp": item.get("timestamp", 0),
                    "evidence_refs": item.get("evidence_refs", []),
                }
            )

        status_counts: dict[str, int] = {}
        for item in items:
            status = item.get("status", "active")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "user_id": user_id,
            "total_items": len(items),
            "only_active": only_active,
            "status_counts": status_counts,
            "categories": grouped,
        }


__all__ = ["InsightService", "InsightRecord"]
