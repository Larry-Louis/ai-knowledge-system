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


def _process_turn(turn_data: dict, qdrant: QdrantStore):
    """Validate, extract, and store a Turn as Memory Unit."""
    turn_text = f"用户: {turn_data.get('user','')}\nAI助手: {turn_data.get('assistant','')}"

    # SLM Validator
    result = _slm_validate(turn_text)
    if not result.get("keep", False):
        return  # drop silently

    # Build a Memory Unit (MU)
    mu_content = result.get("summary") or turn_data.get("user", "")
    mu_type = result.get("type", "fact")
    layer_type = result.get("layer_type", "semantic")
    confidence = result.get("confidence", 0.5)

    # Embed and store
    try:
        embedding = EmbeddingService.embed(mu_content)
    except Exception:
        embedding = [0.0] * Config.EMBEDDING_DIM

    from qdrant_client.models import PointStruct
    point_id = str(uuid.uuid4())
    qdrant.client.upsert(
        collection_name=Config.QDRANT_MEMORY_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "content": mu_content,
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


# ─── SLM Config ────────────────────────────────────────────────

SLM_PROMPT_VERSION = "v1.0"

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

输出格式：
{{"keep": true, "type": "preference", "confidence": 0.85, "summary": "用户喜欢Python"}}
{{"keep": false, "type": "noise", "confidence": 0.3, "summary": ""}}

置信度指南：
- 0.9+：非常确定这条值得记忆
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
    m = re.search(r'\{.*\}', text, re.DOTALL)
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

    return {
        "keep": keep,
        "type": mu_type,
        "layer_type": MU_TYPE_MAP.get(mu_type, "semantic"),
        "confidence": confidence,
        "summary": (result.get("summary") or "").strip(),
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
