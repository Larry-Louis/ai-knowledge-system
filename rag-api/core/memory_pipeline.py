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

from core.prompt_factory import get_memory_validation_prompt
from core.decision_maker import DecisionMaker
from core.text_utils import normalize, detect_polarity, is_duplicate, extract_mus, slm_validate
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


def _store_mu(content: str, mu_type: str, mu_tag: str, layer_type: str,
               importance: float, confidence: float, store_priority: str,
               turn_data: dict, qdrant: QdrantStore):
    """Normalize, dedup, resolve conflict, then store a Memory Unit."""
    content = normalize(content)
    if not content:
        return

    # Dedup check
    is_dup, embedding = is_duplicate(content, qdrant)
    if is_dup:
        return

    # Conflict detection + resolution
    new_polarity = detect_polarity(content)
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
            old_polarity = detect_polarity(old)
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
                    "mu_tag": mu_tag,
                    "layer_type": layer_type,
                    "slm_version": SLM_PROMPT_VERSION,
                    "importance": importance,
                    "confidence": confidence,
                    "store_priority": store_priority,
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
    result = slm_validate(turn_text)
    if not result.get("keep", False):
        return  # drop silently

    # Extract MU(s) — SLM summaries first, then rule-based fallback
    summaries = result.get("summaries") or []
    if not summaries:
        s = (result.get("summary") or "").strip()
        summaries = [s] if s else []
    if not summaries:
        fallback = extract_mus(turn_text, turn_data.get("user", ""))
        summaries = [fallback[0]] if fallback else [turn_data.get("user", "")]
    mu_type = result.get("type", "ENTITY")
    mu_tag = result.get("tag", "noise")
    layer_type = result.get("layer_type", "semantic")
    importance = result.get("importance", 0.0)
    confidence = result.get("confidence", 0.0)
    store_priority = result.get("store_priority", "drop")

    for s in summaries[:3]:  # max 3 MUs per turn
        if s.strip():
            _store_mu(s.strip(), mu_type, mu_tag, layer_type, importance, confidence, store_priority, turn_data, qdrant)


# ─── SLM Config ────────────────────────────────────────────────

_worker_thread = threading.Thread(target=_worker, daemon=True, name="memory-pipeline")
_worker_thread.start()
