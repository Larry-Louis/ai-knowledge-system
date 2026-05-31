"""Stage 0: MVP Memory Pipeline — Turn Builder + Async Queue + SLM Validator + Qdrant Write.

Status: MVP, quality not guaranteed yet.
"""
import json
import time
import uuid
import threading
import queue as pyqueue

import httpx

from core.config import Config
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore


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


# ─── Queue ─────────────────────────────────────────────────────

_memory_queue: pyqueue.Queue = pyqueue.Queue()


def submit_turn(event: MemoryEvent):
    """Submit a MemoryEvent to the async pipeline."""
    _memory_queue.put(event)


# ─── Background Worker ─────────────────────────────────────────

def _worker():
    qdrant = QdrantStore()
    while True:
        try:
            event: MemoryEvent = _memory_queue.get(timeout=1)
        except pyqueue.Empty:
            continue

        try:
            _process_event(event, qdrant)
        except Exception as e:
            print(f"[MemoryPipeline] Error processing turn {event.turn_id}: {e}")


def _process_event(event: MemoryEvent, qdrant: QdrantStore):
    """Validate, extract, and store a MemoryEvent."""
    turn_text = f"用户: {event.user}\nAI助手: {event.assistant}"

    # SLM Validator
    result = _slm_validate(turn_text)
    if not result.get("keep", False):
        return  # drop silently

    # Build a Memory Unit (MU) — Stage 0: just use the validated turn text
    mu_content = result.get("summary") or event.user
    mu_type = result.get("type", "fact")
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
                    "confidence": confidence,
                    "layer": event.layer,
                    "session_id": event.session_id,
                    "turn_id": event.turn_id,
                    "source_user": event.user[:200],
                    "source_assistant": event.assistant[:200],
                    "timestamp": event.timestamp,
                },
            )
        ],
    )


# ─── SLM Validator (MVP) ───────────────────────────────────────

SLM_PROMPT = """你是一个记忆过滤器。判断以下对话内容是否值得长期记忆。
只输出 JSON，不要输出任何其他文字。

值得记忆的内容包括：
- 用户的偏好、习惯、兴趣
- 项目的关键信息、决策、状态
- 重要的事实陈述
- 需要后续跟踪的任务或待办

不值得记忆的内容包括：
- 纯闲聊、打招呼
- 不包含实质信息的确认性回复
- 模糊的、无法独立理解的片段

返回 JSON 格式（只有 JSON，不要其他文字）：
{{"keep": true/false, "type": "preference | fact | project | task | noise", "confidence": 0.0-1.0, "summary": "简短总结"}}

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


def _slm_validate(turn_text: str) -> dict:
    """Call DeepSeek as SLM to validate a conversation turn."""
    api_key = Config.DEEPSEEK_API_KEY
    if not api_key:
        return {"keep": False, "type": "noise", "confidence": 0.0}

    payload = {
        "model": Config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "user", "content": SLM_PROMPT.format(turn=turn_text[:1500])}
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
        result = _safe_parse_json(text)
        if result is None:
            print(f"[SLMValidator] Parse failed, raw: {text[:200]}")
            return {"keep": False, "type": "noise", "confidence": 0.0}
        return result
    except Exception as e:
        print(f"[SLMValidator] Error: {e}")
        return {"keep": False, "type": "noise", "confidence": 0.0}


# ─── Start background worker ───────────────────────────────────

_worker_thread = threading.Thread(target=_worker, daemon=True, name="memory-pipeline")
_worker_thread.start()
