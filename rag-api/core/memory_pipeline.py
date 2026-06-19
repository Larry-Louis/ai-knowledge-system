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
import traceback
import httpx

from core.prompt_factory import get_memory_validation_prompt, SLM_PROMPT_VERSION
from core.decision_maker import DecisionMaker
from core.text_utils import normalize, detect_polarity, is_duplicate, extract_mus, slm_validate
from core.rule_evaluator import probe_structure_score, detect_polarity_score, match_domain_pattern
from core.logger import pipeline_logger
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore
from services.persistent_queue import PersistentQueue


# 内存事件类
class MemoryEvent:
    def __init__(self, user_msg: str, assistant_msg: str,
                 session_id: str, layer: str = 'general'):
        self.turn_id = uuid.uuid4().hex[:12]
        self.user = user_msg
        self.assistant = assistant_msg
        self.session_id = session_id
        self.layer = layer
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            'turn_id': self.turn_id,
            'user': self.user,
            'assistant': self.assistant,
            'session_id': self.session_id,
            'layer': self.layer,
            'timestamp': self.timestamp,
        }


_queue = PersistentQueue()


def submit_turn(event: MemoryEvent):
    _queue.enqueue(event.to_dict())


def _worker():
    qdrant = QdrantStore()
    # [S1-1] 宕机恢复
    _queue.recover_stale(timeout=30)
    last_cleanup = time.time()

    while True:
        now = time.time()
        if now - last_cleanup > 600:
            # [S1-2] 定期清理
            _queue.cleanup(max_age=86400)
            last_cleanup = now

        # [S1-3] 出队
        items = _queue.dequeue(batch_size=1)
        if not items:
            time.sleep(2)
            continue

        item = items[0]
        turn_data = item['data']

        try:
            _process_turn(turn_data, qdrant)
            _queue.mark_done(item['id'])
        except Exception as e:
            _queue.mark_failed(item['id'], str(e))
            print(f"[MemoryPipeline] Detailed Error for turn {turn_data.get('turn_id', '?')}:")
            traceback.print_exc()

def _store_mu(content: str, mu_type: str, mu_tag: str, layer_type: str,
               importance: float, confidence: float, store_priority: str,
               turn_data: dict, qdrant: QdrantStore):
    content = normalize(content)
    if not content: return

    is_dup, embedding = is_duplicate(content, qdrant)
    if is_dup: return

    # Conflict resolution...
    from core.config import Config
    if embedding is None: embedding = [0.0] * Config.EMBEDDING_DIM
    from qdrant_client.models import PointStruct
    qdrant.client.upsert(
        collection_name=Config.QDRANT_MEMORY_COLLECTION,
        points=[PointStruct(id=str(uuid.uuid4()), vector=embedding, payload={'content': content, 'type': 'memory_unit', 'mu_type': mu_type, 'mu_tag': mu_tag, 'layer_type': layer_type, 'slm_version': SLM_PROMPT_VERSION, 'importance': importance, 'confidence': confidence, 'store_priority': store_priority, 'layer': turn_data.get('layer', 'general'), 'session_id': turn_data.get('session_id', ''), 'turn_id': turn_data.get('turn_id', ''), 'timestamp': turn_data.get('timestamp', time.time())})]
    )


def _process_turn(turn_data: dict, qdrant: QdrantStore):
   # [S1-4a] 拼接对话文本
   user_input = turn_data.get("user", "")
   turn_text = f'用户: {user_input}\nAI助手: {turn_data.get("assistant","")}'
   
   # [S1-4-Rule] 综合得分评估：保安系统入口，在SLM评估前进行轻量级过滤。
   score = probe_structure_score(user_input, is_user_turn=True)
   score += detect_polarity_score(turn_text) + match_domain_pattern(turn_text)
   
   # 拦截策略: 如果非常确定是垃圾(<0.1)则跳过
   if score < 0.1: return
   pipeline_logger.debug(f"Turn {turn_data.get('turn_id', 'unknown')}: score={score}, user_input={user_input[:100]}")

   # [S1-4b] SLM 验证前检查，将检查结果和原始信息记录至日志。
   result = slm_validate(turn_text)
   if not result.get('keep', False): return
   pipeline_logger.debug(f"Turn {turn_data.get('turn_id', 'unknown')}: SLM validation result={result}")

   # [S1-4c] DecisionMaker.classify_mu(SLM 结果)
   summaries = result.get('summaries') or []
   if not summaries:
       s = (result.get('summary') or '').strip()
       summaries = [s] if s else []
   
   for s in summaries[:3]:
       if s.strip():
           # [S1-4e] _store_mu(每个摘要)
           _store_mu(s.strip(), result.get('type', 'ENTITY'), result.get('tag', 'noise'), result.get('layer_type', 'semantic'), result.get('importance', 0.0), result.get('confidence', 0.0), result.get('store_priority', 'drop'), turn_data, qdrant)


_worker_thread = threading.Thread(target=_worker, daemon=True, name='memory-pipeline')
_worker_thread.start()
