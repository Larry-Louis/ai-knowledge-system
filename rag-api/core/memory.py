import uuid

from core.config import Config
from core.llm import LLMFactory
from core.prompt import build_prompt
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore
from services.session_store import SessionStore


def _to_dicts(messages: list) -> list[dict]:
    return [m.model_dump() if hasattr(m, "model_dump") else m for m in messages]


class MemoryManager:
    def __init__(self):
        self.qdrant = QdrantStore()
        self.sessions = SessionStore()

    def process_request(self, request_messages: list, session_id: str | None = None) -> dict:
        if not session_id:
            session_id = str(uuid.uuid4())

        messages = _to_dicts(request_messages)

        user_msgs = [m for m in messages if m["role"] == "user"]
        if not user_msgs:
            raise ValueError("No user message found in request")
        last_user_msg = user_msgs[-1]["content"]

        embedding = EmbeddingService.embed(last_user_msg)

        related = self.qdrant.search_memories(
            embedding, session_id, Config.MEMORY_TOP_K
        )
        summary = self.qdrant.get_summary(session_id)

        final_prompt = build_prompt(
            request_messages=messages,
            world_summary=summary,
            related_memories=related,
        )

        self.sessions.add_message(session_id, "user", last_user_msg)
        self.qdrant.upsert_memory(session_id, "user", last_user_msg, embedding)

        llm = LLMFactory.get()
        response = llm.chat(final_prompt)

        self.sessions.add_message(session_id, "assistant", response)
        resp_embedding = EmbeddingService.embed(response)
        self.qdrant.upsert_memory(session_id, "assistant", response, resp_embedding)

        msg_count = self.sessions.get_message_count(session_id)
        if msg_count > 0 and msg_count % (Config.SUMMARY_INTERVAL * 2) == 0:
            self._generate_summary(session_id)

        return {"response": response, "session_id": session_id}

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
            llm = LLMFactory.get()
            summary = llm.chat(prompt)
            embedding = EmbeddingService.embed(summary)
            self.qdrant.save_summary(session_id, summary, embedding)
        except Exception as e:
            print(f"[WARN] Summary generation failed: {e}")
