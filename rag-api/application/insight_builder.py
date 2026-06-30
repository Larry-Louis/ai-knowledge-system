from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from infrastructure.config.config import Config
from infrastructure.logging.logger import pipeline_logger
from application.llm_gateway import get_llm
from application.insight_service import InsightService, InsightRecord
from infrastructure.vector.qdrant_store import QdrantStore


_INSIGHT_CATEGORIES = (
    "identity",
    "preference",
    "project",
    "stack",
    "behavior",
    "goal",
    "experience",
    "general",
)


class InsightBuilder:
    """Phase2 Week2: 从原始记忆生成 Insight 的最小闭环。"""

    def __init__(self, store: QdrantStore | None = None, service: InsightService | None = None):
        self.store = store or QdrantStore()
        self.service = service or InsightService(self.store)

    def build_from_session(self, session_id: str, limit: int = 40) -> dict[str, Any]:
        """基于指定会话的原始记忆生成 Insight，并写回存储。"""
        source_memories = self.store.get_recent_session_memories(
            session_id=session_id,
            limit=limit,
            types=["memory", "memory_unit"],
        )
        if not source_memories:
            return {"session_id": session_id, "created": 0, "categories": {}, "sources": 0}

        grouped = self._group_sources(source_memories)
        candidates = self._compose_candidates(grouped)
        created_records: list[InsightRecord] = []

        for candidate in candidates:
            record = self.service.create_insight(
                user_id=session_id,
                category=candidate["category"],
                content=candidate["content"],
                confidence=candidate["confidence"],
                evidence_refs=candidate["evidence_refs"],
                status="active",
                version=1,
            )
            created_records.append(record)

        report = {
            "session_id": session_id,
            "created": len(created_records),
            "categories": {k: len(v) for k, v in grouped.items() if v},
            "sources": len(source_memories),
            "insight_ids": [r.insight_id for r in created_records],
        }
        pipeline_logger.info(
            "InsightBuilder session=%s sources=%s created=%s categories=%s",
            session_id,
            len(source_memories),
            len(created_records),
            report["categories"],
        )
        return report

    def _group_sources(self, source_memories: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in source_memories:
            content = (item.get("content") or "").strip()
            if not content:
                continue
            category = self._categorize(content, item.get("role", "user"), item.get("type", "memory"))
            grouped[category].append(item)
        return grouped

    def _compose_candidates(self, grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for category in _INSIGHT_CATEGORIES:
            items = grouped.get(category, [])
            if not items:
                continue
            content, confidence = self._summarize_category(category, items)
            evidence_refs = [item["id"] for item in items[:5] if item.get("id")]
            if not content.strip():
                continue
            candidates.append(
                {
                    "category": category,
                    "content": content.strip(),
                    "confidence": confidence,
                    "evidence_refs": evidence_refs,
                }
            )
        return candidates

    def _summarize_category(self, category: str, items: list[dict[str, Any]]) -> tuple[str, float]:
        snippets = [self._shorten(item.get("content", "")) for item in items[:8]]
        if not snippets:
            return "", 0.0

        prompt = [
            {
                "role": "system",
                "content": (
                    "你是 Insight 压缩器。给定若干原始记忆，请输出一条稳定、可复用、" 
                    "不重复的用户画像洞察。只输出 JSON，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "category": category,
                        "requirements": [
                            "总结成一句中文洞察",
                            "保留长期稳定信息",
                            "避免空泛表述",
                            "不要重复原文",
                        ],
                        "memories": snippets,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        try:
            llm = get_llm(role="core")
            response = llm.chat(prompt)
            parsed = self._parse_llm_response(response)
            content = parsed.get("content") or self._fallback_summary(category, snippets)
            confidence = self._safe_confidence(parsed.get("confidence", 0.7), default=0.7)
            return content, confidence
        except Exception as exc:
            pipeline_logger.warning("InsightBuilder LLM fallback for category=%s: %s", category, exc)
            return self._fallback_summary(category, snippets), 0.55

    def _fallback_summary(self, category: str, snippets: list[str]) -> str:
        joined = "；".join(snippets[:3])
        return f"{self._category_label(category)}：{joined}"[:500]

    def _parse_llm_response(self, response: str) -> dict[str, Any]:
        text = (response or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {}

    def _shorten(self, text: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact[:limit]

    def _safe_confidence(self, value: Any, default: float = 0.7) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return default

    def _categorize(self, content: str, role: str, memory_type: str) -> str:
        lower = content.lower()
        if any(marker in content for marker in ("我是", "我负责", "我的工作", "我担任", "我是一名")):
            return "identity"
        if any(marker in content for marker in ("我喜欢", "我讨厌", "我更倾向", "我偏好", "我习惯")):
            return "preference"
        if any(marker in content for marker in ("准备", "计划", "下一步", "打算", "以后", "目标是", "希望")):
            return "goal"
        if any(marker in content for marker in ("一直", "长期", "最近都", "目前一直", "持续", "经常", "习惯")):
            return "behavior"
        if any(marker in content for marker in ("项目", "迁移", "开发", "重构", "上线", "方案", "模块", "系统")):
            return "project"
        if any(marker in content for marker in ("Rust", "Python", "Java", "TypeScript", "React", "FastAPI", "Qdrant", "LLM", "模型", "框架", "API", "库", "版本")):
            return "stack"
        if role == "assistant" and memory_type == "memory_unit":
            return "experience"
        return "general"

    def _category_label(self, category: str) -> str:
        return {
            "identity": "身份画像",
            "preference": "偏好画像",
            "project": "项目画像",
            "stack": "技术栈画像",
            "behavior": "行为模式画像",
            "goal": "目标画像",
            "experience": "经验画像",
            "general": "综合画像",
        }.get(category, "综合画像")


__all__ = ["InsightBuilder"]
