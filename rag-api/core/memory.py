import time
import uuid
import hashlib

from core.config import Config
from core.state import get_active_role
from core.memory_pipeline import MemoryEvent, submit_turn


def _is_auto_task(content: str) -> bool:
    """Detect Open WebUI auto-generated task messages (tags, titles, follow-ups)."""
    if not content:
        return True
    # Task prompts
    if content.startswith("### Task:") or "<chat_history>" in content:
        return True
    # JSON-only responses from auto-tasks
    stripped = content.strip()
    if stripped.startswith("{"):
        import json
        try:
            obj = json.loads(stripped)
            if any(k in obj for k in ("tags", "title", "follow_ups")):
                return True
        except json.JSONDecodeError:
            pass
    return False
from core.llm import LLMFactory
from core.prompt import build_prompt
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore
from services.session_store import SessionStore


def _to_dicts(messages: list) -> list[dict]:
    return [m.model_dump() if hasattr(m, "model_dump") else m for m in messages]


def _merge_memories(session: list[dict], global_: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for m in session + global_:
        key = m["content"][:100]
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result[:12]


class MemoryManager:
    def __init__(self):
        self.qdrant = QdrantStore()
        self.sessions = SessionStore()
        self._model_override = None
        self._last_session_id = None
        self.last_prompt = None

    def _derive_session_id(self, messages: list) -> str:
        """Generate a stable session_id from the first user message in the conversation."""
        for m in messages:
            role = m.role if hasattr(m, "role") else m.get("role")
            content = m.content if hasattr(m, "content") else m.get("content", "")
            if role == "user" and content:
                return "s-" + hashlib.md5(content.encode()).hexdigest()[:16]
        return "s-" + uuid.uuid4().hex[:16]

    def process_request(self, request_messages: list, session_id: str | None = None, model: str | None = None) -> dict:
        self._model_override = model
        if not session_id:
            session_id = self._derive_session_id(request_messages)

        messages = _to_dicts(request_messages)

        user_msgs = [m for m in messages if m["role"] == "user"]
        if not user_msgs:
            raise ValueError("No user message found in request")
        last_user_msg = user_msgs[-1]["content"]

        embedding = EmbeddingService.embed(last_user_msg)
        active_role = get_active_role()

        # Search layers: "core" always + active role layer
        search_layers = ["core"]
        if active_role != "core":
            search_layers.append(active_role)

        is_new_session = (session_id != self._last_session_id)
        self._last_session_id = session_id

        related = self.qdrant.search_memories(
            embedding, session_id, Config.MEMORY_TOP_K
        )
        global_memories = self.qdrant.search_global_memories(embedding, top_k=6, layers=search_layers)

        # 新会话时带 2 条最近跨会话记忆作为预热，同会话时跳过（因为 messages 已有完整历史）
        recent_global = []
        if is_new_session:
            recent_global = self.qdrant.get_recent_global_memories(
                exclude_session=session_id, limit=2, layers=search_layers
            )

        all_memories = _merge_memories(related, global_memories + recent_global)
        summary = self.qdrant.get_summary()

        # Search ONLY actively mounted documents for relevant context
        # Core write mode: check if user message contains a save trigger
        from core.state import get_active_doc_ids, get_core_write_mode
        if get_core_write_mode():
            for trigger in Config.CORE_TRIGGERS:
                if trigger in last_user_msg:
                    core_text = last_user_msg.split(trigger, 1)[1].strip()
                    if core_text:
                        core_emb = EmbeddingService.embed(core_text)
                        self.qdrant.upsert_memory(
                            session_id, "system", core_text, core_emb,
                            layer=Config.CORE_LAYER
                        )
                    break

        active_docs = get_active_doc_ids()
        doc_chunks = []
        if active_docs:
            doc_chunks = self.qdrant.search_documents(embedding, top_k=4, doc_ids=list(active_docs))

        final_prompt = build_prompt(
            request_messages=messages,
            world_summary=summary,
            related_memories=all_memories,
            document_chunks=doc_chunks,
        )
        self.last_prompt = {
            "session_id": session_id,
            "debug_info": {"related": len(all_memories), "summary": bool(summary), "docs": len(doc_chunks)},
            "model": model or Config.DEEPSEEK_MODEL,
            "timestamp": int(time.time()),
            "messages": final_prompt,
            "related_memories": all_memories,
            "world_summary": summary,
            "document_chunks": doc_chunks,
        }

        self.sessions.add_message(session_id, "user", last_user_msg)
        # Skip storing auto-task messages as memories
        if not _is_auto_task(last_user_msg):
            self.qdrant.upsert_memory(session_id, "user", last_user_msg, embedding, layer=active_role)

        model_override = getattr(self, '_model_override', None)
        if not model_override and active_role in ['story', 'docreader']:
            llm = LLMFactory.get(provider='deepseek', model='deepseek-v4-flash')
        else:
            llm = LLMFactory.get(model=model_override)
        response = llm.chat(final_prompt)

        self.sessions.add_message(session_id, "assistant", response)
        if not _is_auto_task(response):
            resp_embedding = EmbeddingService.embed(response)
            self.qdrant.upsert_memory(session_id, "assistant", response, resp_embedding, layer=active_role)

        # Stage 0: Submit Turn to async memory pipeline
        event = MemoryEvent(
            user_msg=last_user_msg,
            assistant_msg=response,
            session_id=session_id,
            layer=active_role,
        )
        submit_turn(event)
        if Config.TEST_MODE:
            from core.logger import pipeline_logger
            pipeline_logger.debug(f"Turn {event.turn_id} submitted: user_input={last_user_msg[:50]}, assistant_response={response[:50]}")

        msg_count = self.sessions.get_message_count(session_id)
        if msg_count > 0 and msg_count % (Config.SUMMARY_INTERVAL * 2) == 0:
            self._generate_summary(session_id)

        reasoning = getattr(llm, 'last_reasoning', None)
        return {"response": response, "session_id": session_id, "reasoning": reasoning}

    def _generate_summary(self, session_id: str):
        recent = self.sessions.get_recent(session_id, Config.SHORT_TERM_SIZE)
        if not recent:
            return

        history_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI助手'}: {m['content'][:200]}"
            for m in recent
        )

        prompt = [
            {
                "role": "system",
                "content": "你是世界观摘要生成器。基于对话历史提取关键设定、角色、事件，生成简洁的世界观摘要。",
            },
            {
                "role": "user",
                "content": f"基于以下对话内容，生成世界观摘要（包含核心设定、重要角色、关键事件、规则）：\n\n{history_text}",
            },
        ]

        try:
            llm = LLMFactory.get(model=self._model_override)
            summary = llm.chat(prompt)
            embedding = EmbeddingService.embed(summary)
            self.qdrant.save_summary(summary, embedding)
        except Exception as e:
            print(f"[WARN] Summary generation failed: {e}")
