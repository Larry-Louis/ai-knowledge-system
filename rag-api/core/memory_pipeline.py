"""Stage 1: Persistent Queue + Retry + Worker.

Key changes from Stage 0:
- SQLite-backed queue (survives restarts)
- Recovery mechanism (reprocess stuck items after crash)
- Retry with backoff (max 3 retries)
- Cleanup old completed items
"""
import json
import time
import uuid
import threading

import httpx

from core.config import Config
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore
from services.persistent_queue import PersistentQueue


# ─── Memory Event ──────────────────────────────────────────────

class MemoryEvent:
    """A Memory Event = one Conversation Turn (user + assistant)."""
    def __init__(self, user_msg: str, assistant_msg: str,
                 session_id: str, layer: str = "general"):
        self.turn_id = uuid.uuid4().hex[:12]
        self.user = user_msg
        self.assistant = assistant_msg
        self.session_id = session_id
        self.layer = layer
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "user": self.user,
            "assistant": self.assistant,
            "session_id": self.session_id,
            "layer": self.layer,
            "timestamp": self.timestamp,
        }


# ─── Queue (Persistent) ────────────────────────────────────────

_queue = PersistentQueue()


def submit_turn(event: MemoryEvent):
    """Submit a MemoryEvent to the persistent queue."""
    _queue.enqueue(event.to_dict())


# ─── Background Worker ─────────────────────────────────────────

def _worker():
    qdrant = QdrantStore()
    # Recover any items stuck from a previous crash
    _queue.recover_stale(timeout=30)
    last_cleanup = time.time()

    while True:
        # Periodic cleanup (every 10 minutes)
        now = time.time()
        if now - last_cleanup > 600:
            _queue.cleanup(max_age=86400)
            last_cleanup = now

        # Dequeue next item (non-blocking, 2s poll)
        items = _queue.dequeue(batch_size=1)
        if not items:
            time.sleep(2)
            continue

        item = items[0]
        turn_data = item["data"]

        try:
            _process_turn(turn_data, qdrant)
            _queue.mark_done(item["id"])
        except Exception as e:
            _queue.mark_failed(item["id"], str(e))
            print(f"[MemoryPipeline] Failed turn {turn_data.get('turn_id','?')}: {e}")


def _store_mu(content: str, mu_type: str, layer_type: str, confidence: float,
               turn_data: dict, qdrant: QdrantStore):
    """Normalize, dedup, resolve conflict, then store a Memory Unit."""
    content = _normalize(content)
    if not content:
        return

    # Dedup check
    is_dup, embedding = _is_duplicate(content, qdrant)
    if is_dup:
        return

    # Conflict detection + resolution
    new_polarity = _detect_polarity(content)
    if new_polarity != 0 and embedding:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        similar = qdrant.client.query_points(
            collection_name=Config.QDRANT_MEMORY_COLLECTION,
            query=embedding,
            query_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="memory_unit")),
            ]),
            limit=5,
        )
        for p in similar.points:
            if p.score < CONFLICT_THRESHOLD:
                continue
            old = p.payload.get("content", "")
            old_polarity = _detect_polarity(old)
            if old_polarity != 0 and old_polarity != new_polarity:
                # Conflict! Newest overrides old
                qdrant.client.delete(
                    collection_name=Config.QDRANT_MEMORY_COLLECTION,
                    points_selector=[p.id],
                )
                break

    if embedding is None:
        embedding = [0.0] * Config.EMBEDDING_DIM

    from qdrant_client.models import PointStruct
    qdrant.client.upsert(
        collection_name=Config.QDRANT_MEMORY_COLLECTION,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "content": content,
                    "type": "memory_unit",
                    "mu_type": mu_type,
                    "layer_type": layer_type,
                    "slm_version": SLM_PROMPT_VERSION,
                    "confidence": confidence,
                    "layer": turn_data.get("layer", "general"),
                    "session_id": turn_data.get("session_id", ""),
                    "turn_id": turn_data.get("turn_id", ""),
                    "source_user": (turn_data.get("user") or "")[:200],
                    "source_assistant": (turn_data.get("assistant") or "")[:200],
                    "timestamp": turn_data.get("timestamp", time.time()),
                },
            )
        ],
    )


def _process_turn(turn_data: dict, qdrant: QdrantStore):
    """Validate, extract, and store a Turn as Memory Unit(s)."""
    turn_text = f"用户: {turn_data.get('user','')}\nAI助手: {turn_data.get('assistant','')}"

    # SLM Validator
    result = _slm_validate(turn_text)
    if not result.get("keep", False):
        return  # drop silently

    # Extract MU(s) — SLM summaries first, then rule-based fallback
    summaries = result.get("summaries") or []
    if not summaries:
        s = (result.get("summary") or "").strip()
        summaries = [s] if s else []
    if not summaries:
        fallback = _extract_mus(turn_text, turn_data.get("user", ""))
        summaries = [fallback[0]] if fallback else [turn_data.get("user", "")]
    mu_type = result.get("type", "fact")
    layer_type = result.get("layer_type", "semantic")
    confidence = result.get("confidence", 0.5)

    for s in summaries[:3]:  # max 3 MUs per turn
        if s.strip():
            _store_mu(s.strip(), mu_type, layer_type, confidence, turn_data, qdrant)


# ─── SLM Config ────────────────────────────────────────────────

SLM_PROMPT_VERSION = "v2.2"

SLM_PROMPT = """[Version: {version}]
你是一个记忆过滤器。判断以下对话内容是否值得长期记忆。
只输出纯 JSON，不要任何其他文字。

值得记忆（keep=true）的内容：
- 用户的偏好、习惯、兴趣（type=preference）
- 项目的关键信息、决策、状态（type=project）
- 重要的事实陈述（type=fact）
- 需要后续跟踪的任务或待办（type=task）
- 用户告知的个人信息（type=preference）

不值得记忆（keep=false）的内容：
- 纯闲聊、打招呼（type=noise）
- 确认性回复、无实质信息（type=noise）

如果一条对话包含多个独立信息点，用 summaries 数组输出多条。

输出格式（单条）：
{{"keep": true, "type": "preference", "confidence": 0.85, "summary": "用户喜欢Python", "summaries": []}}
输出格式（多条）：
{{"keep": true, "type": "fact", "confidence": 0.8, "summary": "", "summaries": ["用户技术栈是Python", "用户从事AI开发"]}}

置信度指南：
- 0.9+：非常确定
- 0.6-0.9：可能值得
- 0.3-0.6：不确定
- 低于0.3：很可能不值得

对话内容：
{turn}"""


def _safe_parse_json(text: str) -> dict | None:
    """Try to extract a JSON object from model output."""
    import re
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        # If it's a bare string like "keep", fall through to last resort
    except json.JSONDecodeError:
        pass
    # Try to find {...} in the string
    m = re.search(r'\{.*?\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Last resort: check if the model said "keep" or "drop" or true/false
    lower = text.lower().strip().strip('"').strip()
    if lower in ('keep', 'true'):
        return {"keep": True, "type": "fact", "confidence": 0.6, "summary": text}
    if lower in ('drop', 'false'):
        return {"keep": False, "type": "noise", "confidence": 0.6}
    if '"keep"' in text:
        return {"keep": 'true' in lower, "type": "fact", "confidence": 0.5}
    return None


# ─── Normalizer ────────────────────────────────────────────────

_TERM_MAP = {
    "autosar": "AUTOSAR",
    "rag": "RAG",
    "ai": "AI",
    "llm": "LLM",
    "api": "API",
    "slm": "SLM",
    "qdrant": "Qdrant",
    "ollama": "Ollama",
    "deepseek": "DeepSeek",
    "python": "Python",
    "java": "Java",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "sqlite": "SQLite",
}


def _normalize(text: str) -> str:
    """Normalize MU text: unify subject, standardize terms, dedent."""
    text = text.strip()
    if not text:
        return text
    # Subject unification: sentence-starting 我 → 用户
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("我") and not line.startswith("我们"):
            line = "用户" + line[1:]
        elif line.startswith("我们"):
            line = "用户" + line[2:]
        # Term normalization (case-insensitive)
        for key, val in _TERM_MAP.items():
            esc = re.escape(key)
            line = re.sub(rf'(?i)(^|[^a-zA-Z]){esc}([^a-zA-Z]|$)', rf'\1{val}\2', line)
        lines.append(line)
    return "\n".join(lines)


DEDUP_THRESHOLD = 0.90
CONFLICT_THRESHOLD = 0.80  # similarity for conflict detection → override with newest

# Simplified polarity keywords for conflict detection
_POSITIVE = {"喜欢", "爱", "可以", "会", "要", "想", "支持", "推荐"}
_NEGATIVE = {"不喜欢", "不爱", "不好", "不可以", "不会", "不是", "不要", "不想",
             "讨厌", "恨", "反对", "拒绝", "无法", "不能"}


def _detect_polarity(text: str) -> int:
    """Rough polarity: 1 = positive, -1 = negative, 0 = neutral.
    Negative checked first. Pure count-based to avoid substring conflicts."""
    text_lower = text.lower()
    pos_count = sum(text_lower.count(w) for w in _POSITIVE)
    neg_count = sum(text_lower.count(w) for w in _NEGATIVE)
    # Filter out pos matches that are substrings of neg matches
    for nw in _NEGATIVE:
        for pw in _POSITIVE:
            if pw in nw:  # e.g. '喜欢' in '不喜欢'
                overlap = text_lower.count(nw)
                pos_count = max(0, pos_count - overlap)
    return 1 if pos_count > neg_count else (-1 if neg_count > pos_count else 0)





def _is_duplicate(content: str, qdrant: QdrantStore) -> tuple[bool, list[float] | None]:
    """Check if similar MU exists. Returns (is_dup, embedding)."""
    try:
        embedding = EmbeddingService.embed(content)
    except Exception:
        return False, None

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    results = qdrant.client.query_points(
        collection_name=Config.QDRANT_MEMORY_COLLECTION,
        query=embedding,
        query_filter=Filter(must=[
            FieldCondition(key="type", match=MatchValue(value="memory_unit")),
        ]),
        limit=5,
    )
    for p in results.points:
        if p.score >= DEDUP_THRESHOLD:
            return True, embedding
    return False, embedding


# ─── Memory Unit Extractor (Rule-based) ────────────────────────

import re

_SEPARATORS = re.compile(r'(?:并且|而且|还|以及|同时|，|。|；|、)')


def _extract_mus(turn_text: str, user_msg: str) -> list[str]:
    """Simple rule-based extraction: split by conjunctions/punctuation."""
    candidates = [s.strip() for s in _SEPARATORS.split(user_msg) if len(s.strip()) > 4]
    return candidates[:5] if candidates else [user_msg[:200]]


# ─── Type Mapping ──────────────────────────────────────────────

MU_TYPE_MAP = {
    "preference": "semantic",
    "fact": "semantic",
    "project": "episodic",
    "task": "episodic",
    "noise": "drop",
}

CONFIDENCE_THRESHOLD = 0.3  # below this → drop


def _classify_mu(result: dict) -> dict:
    """Apply type mapping and confidence thresholds."""
    mu_type = result.get("type", "noise")
    confidence = max(0.0, min(1.0, result.get("confidence", 0.5)))
    keep = result.get("keep", False) and confidence >= CONFIDENCE_THRESHOLD

    raw_summaries = result.get("summaries", [])
    if isinstance(raw_summaries, list) and len(raw_summaries) > 0:
        summaries = [s.strip() for s in raw_summaries if s and s.strip()]
    else:
        s = (result.get("summary") or "").strip()
        summaries = [s] if s else []

    return {
        "keep": keep,
        "type": mu_type,
        "layer_type": MU_TYPE_MAP.get(mu_type, "semantic"),
        "confidence": confidence,
        "summary": summaries[0] if summaries else "",
        "summaries": summaries,
    }


def _slm_validate(turn_text: str) -> dict:
    """Call DeepSeek as SLM, then apply classification rules."""
    api_key = Config.DEEPSEEK_API_KEY
    if not api_key:
        return {"keep": False, "type": "noise", "confidence": 0.0, "layer_type": "drop"}

    payload = {
        "model": Config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "user", "content": SLM_PROMPT.format(
                version=SLM_PROMPT_VERSION, turn=turn_text[:1500]
            )}
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(
            f"{Config.DEEPSEEK_BASE_URL}/chat/completions",
            json=payload, headers=headers, timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        raw = _safe_parse_json(text)
        if raw is None:
            print(f"[SLMValidator] Parse failed, raw: {text[:200]}")
            return {"keep": False, "type": "noise", "confidence": 0.0, "layer_type": "drop"}
        return _classify_mu(raw)
    except Exception as e:
        print(f"[SLMValidator] Error: {e}")
        return {"keep": False, "type": "noise", "confidence": 0.0, "layer_type": "drop"}


# ─── Start background worker ───────────────────────────────────

_worker_thread = threading.Thread(target=_worker, daemon=True, name="memory-pipeline")
_worker_thread.start()
