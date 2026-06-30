from __future__ import annotations

import argparse
import json
import math
import sys
import time
import types
from collections import Counter
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Runtime stubs
# ---------------------------------------------------------------------------
# The workspace currently does not guarantee qdrant_client is installed in the
# active venv. This script is intended to be self-contained, so we provide a
# minimal stub before importing project modules that depend on it.
if "qdrant_client" not in sys.modules:
    qdrant_client = types.ModuleType("qdrant_client")
    qdrant_models = types.ModuleType("qdrant_client.models")

    class _DummyQdrantClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_collections(self):
            return types.SimpleNamespace(collections=[])

        def create_collection(self, *args, **kwargs):
            return None

        def upsert(self, *args, **kwargs):
            return None

        def query_points(self, *args, **kwargs):
            return types.SimpleNamespace(points=[])

        def scroll(self, *args, **kwargs):
            return ([], None)

        def create_payload_index(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

    class _DummyValue:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    for name in [
        "Distance",
        "VectorParams",
        "PointStruct",
        "Filter",
        "FieldCondition",
        "MatchValue",
        "FilterSelector",
        "MatchAny",
    ]:
        setattr(qdrant_models, name, type(name, (), {}))

    qdrant_models.PayloadSchemaType = types.SimpleNamespace(INTEGER="INTEGER", KEYWORD="KEYWORD")
    qdrant_client.QdrantClient = _DummyQdrantClient
    qdrant_client.models = qdrant_models
    sys.modules["qdrant_client"] = qdrant_client
    sys.modules["qdrant_client.models"] = qdrant_models

from application.insight_builder import InsightBuilder
from application.insight_service import InsightService
from infrastructure.embedding.embedding import EmbeddingService
from domain.memory.math_utils import cosine_similarity


SAMPLES = [
    {"role": "user", "content": "我最近一直在研究Adaptive AUTOSAR，准备把公司的通信模块迁移到ARA::COM。"},
    {"role": "user", "content": "我喜欢用Rust和Python做系统工具开发。"},
    {"role": "user", "content": "我目前负责一个AI知识库项目，目标是降低Prompt Token。"},
    {"role": "user", "content": "我打算下一步把Qdrant引入到检索链路里。"},
    {"role": "user", "content": "我经常整理对话纪要，并且会保留版本历史。"},
]


def load_replay_records(input_file: str | None) -> list[dict[str, Any]]:
    if not input_file:
        return []

    path = Path(input_file)
    if not path.exists():
        raise FileNotFoundError(f"replay file not found: {path}")

    records: list[dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid jsonl at line {line_no}: {exc}") from exc
            if isinstance(record, dict):
                records.append(record)
        return records

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("turns"), list):
        for item in payload["turns"]:
            if isinstance(item, dict):
                records.append(item)
        return records

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    raise ValueError("unsupported replay file format")


class FakeLLM:
    def chat(self, messages: list[dict]) -> str:
        payload = {}
        if messages:
            user_msg = messages[-1].get("content", "")
            try:
                payload = json.loads(user_msg)
            except Exception:
                payload = {}

        category = payload.get("category", "general")
        snippets = payload.get("memories", []) or []
        lead = snippets[0] if snippets else ""
        content = self._render_content(category, lead)
        return json.dumps({"content": content, "confidence": 0.78}, ensure_ascii=False)

    def _render_content(self, category: str, lead: str) -> str:
        labels = {
            "identity": "用户身份画像",
            "preference": "用户偏好画像",
            "project": "用户项目画像",
            "stack": "用户技术栈画像",
            "behavior": "用户行为模式画像",
            "goal": "用户目标画像",
            "experience": "用户经验画像",
            "general": "用户综合画像",
        }
        label = labels.get(category, "用户综合画像")
        lead = (lead or "").strip()
        if not lead:
            return label
        return f"{label}：{lead[:120]}"


class FakeInsightStore:
    def __init__(self, session_memories: dict[str, list[dict[str, Any]]] | None = None):
        self.session_memories = session_memories or {}
        self.insights: list[dict[str, Any]] = []
        self._counter = 0

    def get_recent_session_memories(
        self,
        session_id: str,
        limit: int = 40,
        types: list[str] | None = None,
        layers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        _ = types, layers
        return list(self.session_memories.get(session_id, []))[:limit]

    def upsert_insight(
        self,
        user_id: str,
        category: str,
        content: str,
        embedding: list[float],
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
        status: str = "active",
        version: int = 1,
        insight_id: str | None = None,
    ) -> str:
        record_id = insight_id or f"insight-{self._counter + 1}"
        self._counter += 1
        existing = None
        for item in self.insights:
            if item["insight_id"] == record_id:
                existing = item
                break
        payload = {
            "insight_id": record_id,
            "user_id": user_id,
            "category": category,
            "content": content,
            "embedding": embedding,
            "confidence": max(0.0, min(1.0, confidence)),
            "evidence_refs": list(evidence_refs or []),
            "status": status,
            "version": version,
            "timestamp": time.time(),
        }
        if existing is None:
            self.insights.append(payload)
        else:
            existing.update(payload)
        return record_id

    def search_insights(
        self,
        embedding: list[float],
        user_id: str,
        top_k: int | None = None,
        categories: list[str] | None = None,
        only_active: bool = True,
    ) -> list[dict[str, Any]]:
        limit = top_k or 6
        items = []
        for item in self.insights:
            if item.get("user_id") != user_id:
                continue
            if categories and item.get("category") not in categories:
                continue
            if only_active and item.get("status") != "active":
                continue
            score = cosine_similarity(embedding, item.get("embedding", []))
            items.append({**item, "score": score})
        items.sort(key=lambda x: x["score"], reverse=True)
        return items[:limit]

    def get_recent_insights(
        self,
        user_id: str,
        limit: int = 20,
        categories: list[str] | None = None,
        only_active: bool = True,
    ) -> list[dict[str, Any]]:
        items = []
        for item in self.insights:
            if item.get("user_id") != user_id:
                continue
            if categories and item.get("category") not in categories:
                continue
            if only_active and item.get("status") != "active":
                continue
            items.append(item)
        items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return items[:limit]


def simple_embed(text: str) -> list[float]:
    """Deterministic local embedding for offline evaluation."""
    text = (text or "").lower()
    vec = [0.0] * 64
    for index, char in enumerate(text):
        bucket = (ord(char) * 31 + index) % len(vec)
        vec[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


class _PatchedEmbeddingService:
    @staticmethod
    def embed(text: str) -> list[float]:
        return simple_embed(text)


class _PatchedLLM:
    @staticmethod
    def get(*args, **kwargs):
        return FakeLLM()


def build_sample_session(session_id: str) -> dict[str, list[dict[str, Any]]]:
    return {
        session_id: [
            {"id": "m1", "content": SAMPLES[0]["content"], "role": "user", "type": "memory", "layer": "general"},
            {"id": "m2", "content": SAMPLES[1]["content"], "role": "user", "type": "memory", "layer": "general"},
            {"id": "m3", "content": SAMPLES[2]["content"], "role": "user", "type": "memory", "layer": "general"},
            {"id": "m4", "content": SAMPLES[3]["content"], "role": "user", "type": "memory", "layer": "general"},
            {"id": "m5", "content": SAMPLES[4]["content"], "role": "user", "type": "memory", "layer": "general"},
        ]
    }


def build_sessions_from_records(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sessions: dict[str, list[dict[str, Any]]] = {}
    for index, record in enumerate(records, start=1):
        session_id = str(record.get("session_id") or f"replay-{index}")
        messages = record.get("messages")
        if isinstance(messages, list) and messages:
            normalized = [m for m in messages if isinstance(m, dict) and m.get("content")]
        else:
            user_msg = record.get("user") or record.get("question") or record.get("content")
            assistant_msg = record.get("assistant") or record.get("answer") or record.get("response") or ""
            normalized = []
            if user_msg:
                normalized.append({"role": "user", "content": str(user_msg)})
            if assistant_msg:
                normalized.append({"role": "assistant", "content": str(assistant_msg)})
        if not normalized:
            continue

        sessions.setdefault(session_id, [])
        for message_index, message in enumerate(normalized, start=1):
            sessions[session_id].append(
                {
                    "id": record.get("turn_id") or f"{session_id}-{index}-{message_index}",
                    "content": message.get("content", ""),
                    "role": message.get("role", "user"),
                    "type": record.get("type", "memory"),
                    "layer": record.get("layer", "general"),
                }
            )
    return sessions


def run_builder_report(session_id: str) -> dict[str, Any]:
    store = FakeInsightStore(build_sample_session(session_id))

    # Patch project dependencies for offline evaluation.
    import application.insight_builder as insight_builder_module
    import application.insight_service as insight_service_module

    insight_builder_module.get_llm = lambda role=None: FakeLLM()
    insight_builder_module.EmbeddingService = _PatchedEmbeddingService
    insight_service_module.EmbeddingService = _PatchedEmbeddingService

    service = InsightService(store)
    builder = InsightBuilder(store, service)
    report = builder.build_from_session(session_id)
    profile = service.build_user_profile_snapshot(session_id)

    category_counts = Counter(item["category"] for item in store.insights)
    compression_ratio = round(report["created"] / max(1, report["sources"]), 4)
    return {
        "session_id": session_id,
        "sources": report["sources"],
        "created": report["created"],
        "compression_ratio": compression_ratio,
        "category_counts": dict(category_counts),
        "insights": [
            {
                "insight_id": item["insight_id"],
                "category": item["category"],
                "status": item["status"],
                "version": item["version"],
                "confidence": item["confidence"],
                "content": item["content"],
            }
            for item in store.insights
        ],
        "profile": profile,
    }


def run_multi_session_report(session_sessions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    reports = []
    total_sources = 0
    total_created = 0
    category_counter: Counter[str] = Counter()

    for session_id in sorted(session_sessions.keys()):
        store = FakeInsightStore({session_id: session_sessions[session_id]})

        import application.insight_builder as insight_builder_module
        import application.insight_service as insight_service_module

        insight_builder_module.get_llm = lambda role=None: FakeLLM()
        insight_builder_module.EmbeddingService = _PatchedEmbeddingService
        insight_service_module.EmbeddingService = _PatchedEmbeddingService

        service = InsightService(store)
        builder = InsightBuilder(store, service)
        report = builder.build_from_session(session_id)
        profile = service.build_user_profile_snapshot(session_id)

        reports.append(
            {
                "session_id": session_id,
                "sources": report["sources"],
                "created": report["created"],
                "compression_ratio": round(report["created"] / max(1, report["sources"]), 4),
                "categories": report["categories"],
                "profile_total": profile["total_insights"],
            }
        )
        total_sources += report["sources"]
        total_created += report["created"]
        category_counter.update(item["category"] for item in store.insights)

    return {
        "sessions": reports,
        "totals": {
            "sessions": len(reports),
            "sources": total_sources,
            "created": total_created,
            "compression_ratio": round(total_created / max(1, total_sources), 4),
            "category_counts": dict(category_counter),
        },
    }


def run_conflict_probe() -> dict[str, Any]:
    store = FakeInsightStore()

    import application.insight_service as insight_service_module

    insight_service_module.EmbeddingService = _PatchedEmbeddingService
    service = InsightService(store)

    first = service.create_insight(
        user_id="conflict-session",
        category="preference",
        content="我喜欢 Rust，不喜欢 Java。",
        confidence=0.9,
        evidence_refs=["seed-a"],
    )
    second = service.create_insight(
        user_id="conflict-session",
        category="preference",
        content="我不喜欢 Rust，更倾向于 Python。",
        confidence=0.8,
        evidence_refs=["seed-b"],
    )

    recent = store.get_recent_insights("conflict-session", limit=10)
    return {
        "first": first.__dict__,
        "second": second.__dict__,
        "recent": [
            {
                "insight_id": item["insight_id"],
                "category": item["category"],
                "status": item["status"],
                "version": item["version"],
                "confidence": item["confidence"],
                "content": item["content"],
                "evidence_refs": item["evidence_refs"],
            }
            for item in recent
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 Insight offline evaluation")
    parser.add_argument("--session-id", default="phase2-eval", help="Session id for the sample run")
    parser.add_argument("--input-file", default="", help="Optional JSON/JSONL replay file")
    args = parser.parse_args()

    replay_records = load_replay_records(args.input_file) if args.input_file else []
    if replay_records:
        session_sessions = build_sessions_from_records(replay_records)
        builder_report = run_multi_session_report(session_sessions)
    else:
        builder_report = run_builder_report(args.session_id)

    conflict_report = run_conflict_probe()

    output = {
        "builder": builder_report,
        "conflict_probe": conflict_report,
        "done_criteria_hint": {
            "compression_target": "100 条碎片 -> 5~15 条洞察",
            "status": "active/conflicted",
            "versioning": "递增并保留历史状态",
            "replay_mode": "支持 JSONL/JSON 回放集",
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
