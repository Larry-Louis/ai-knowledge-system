import time
import uuid
import hashlib

from infrastructure.config.config import Config
from infrastructure.runtime.state import get_active_role
from application.memory_pipeline_service import MemoryEvent, submit_turn
from infrastructure.logging.logger import pipeline_logger


def _is_auto_task(content: str, source: str = "user") -> bool:
    """检测 Open WebUI 自动生成任务消息 (tags, titles, follow-ups)."""
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
from infrastructure.llm.llm_client import LLMFactory
from prompts.prompt import build_prompt
from infrastructure.embedding.embedding import EmbeddingService
from infrastructure.vector.qdrant_store import QdrantStore
from infrastructure.session.session_store import SessionStore


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
        """
        [S0-2] 至 [S0-13] 核心记忆处理工作流

        主要工作流：
        [S0-2] 会话 ID 推导：如果没有提供 session_id，则根据第一条用户消息生成稳定的会话 ID
        [S0-3] 用户消息向量化：使用 EmbeddingService 将最后一条用户消息转换为向量
        [S0-4] 三重记忆检索：
            - 当前会话记忆 (search_memories)
            - 全局跨会话记忆 (search_global_memories)
            - 新会话时额外获取最近跨会话记忆 (get_recent_global_memories)
        [S0-5] 记忆合并去重：合并当前会话记忆和全局记忆，去重后最多保留 12 条
        [S0-6] 摘要检索 + 文档检索：获取世界观摘要和活跃文档的相关片段
        [S0-7] 核心写入触发（可选）：如果 core_write_mode 启用且消息包含触发词，将后续文本写入核心层
        [S0-8] 构建 RAG 提示：将系统提示、世界观摘要、相关记忆、文档片段组合成最终提示
        [S0-9] LLM 调用：根据角色选择模型（story/docreader 使用 deepseek-v4-flash，其他使用默认模型）
        [S0-10] 同步写入 Qdrant：将用户消息和助手回复写入记忆存储
        [S0-11] 同步写入 Qdrant（同上）
        [S0-12] 提交异步管道任务：将本轮对话提交到异步记忆处理管道 (MemoryEvent)
        [S0-13] 条件性摘要生成：每 SUMMARY_INTERVAL*2 条消息触发一次世界观摘要生成
        """
        self._model_override = model
        if not session_id:
            # [S0-2] 会话 ID 推导
            session_id = self._derive_session_id(request_messages)

        messages = _to_dicts(request_messages)

        user_msgs = [m for m in messages if m["role"] == "user"]
        if not user_msgs:
            raise ValueError("No user message found in request")
        last_user_msg = user_msgs[-1]["content"]

        # [S0-3] 用户消息向量化
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
        # [S0-4] 三重记忆检索

        # 新会话时带 2 条最近跨会话记忆作为预热，同会话时跳过（因为 messages 已有完整历史）
        recent_global = []
        if is_new_session:
            recent_global = self.qdrant.get_recent_global_memories(
                exclude_session=session_id, limit=2, layers=search_layers
            )

        all_memories = _merge_memories(related, global_memories + recent_global)
        summary = self.qdrant.get_summary()
        # [S0-5] 记忆合并去重，[S0-6] 摘要检索 + 文档检索 (get_summary 在前)

        # Search ONLY actively mounted documents for relevant context
        # Core write mode: check if user message contains a save trigger
        from infrastructure.runtime.state import get_active_doc_ids, get_core_write_mode
        if get_core_write_mode():
            for trigger in Config.CORE_TRIGGERS:
                if trigger in last_user_msg:
        # [S0-7] 核心写入触发（可选）
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
        # [S0-8] 构建 RAG 提示
        final_prompt = build_prompt(
           request_messages=messages,
           overall_summary=summary,
           related_memories=all_memories,
           document_chunks=doc_chunks,
       )
        self.last_prompt = {
           "session_id": session_id,
           "debug_info": {"related": len(all_memories), "summary": bool(summary), "docs": len(doc_chunks)},
            "layer_stats": {m.get('layer', 'unknown'): sum(1 for x in all_memories if x.get('layer') == m.get('layer', 'unknown')) for m in all_memories},
            "model": model or Config.DEEPSEEK_MODEL,
            "timestamp": int(time.time()),
            "messages": final_prompt,
            "related_memories": all_memories,
            "overall_summary": summary,
            "document_chunks": doc_chunks,
        }

        self.sessions.add_message(session_id, "user", last_user_msg)
        # Skip storing auto-task messages as memories
        if not _is_auto_task(last_user_msg, source="user"):
            # [S0-10] 存储用户消息为记忆，同步写入 Qdrant；
            self.qdrant.upsert_memory(session_id, "user", last_user_msg, embedding, layer=active_role)

        model_override = getattr(self, '_model_override', None)
        if not model_override and active_role in ['story', 'docreader']:
            llm = LLMFactory.get(provider='deepseek', model='deepseek-v4-flash')
        else:
            llm = LLMFactory.get(model=model_override)
        # [S0-9] LLM 调用
        response = llm.chat(final_prompt)

        self.sessions.add_message(session_id, "assistant", response)
        if not _is_auto_task(response, source="assistant"):
           resp_embedding = EmbeddingService.embed(response)
           # [S0-11] 存储助手回复为记忆，同步写入 Qdrant；
           self.qdrant.upsert_memory(session_id, "assistant", response, resp_embedding, layer=active_role)

        
        is_auto_task = _is_auto_task(last_user_msg, source="user") or _is_auto_task(response, source="assistant")
        if not is_auto_task:
            # [S0-12] 提交异步管道任务，普通对话 → 提交到异步记忆处理管道
            event = MemoryEvent(
               user_msg=last_user_msg,
               assistant_msg=response,
               session_id=session_id,
               layer=active_role,
            )
            # Stage 0: 把 turn 提交到异步队列，Stage 1: 异步处理管道会进行去重、SLM 验证、规则评估等操作
            submit_turn(event)
            if Config.TEST_MODE:
                from infrastructure.logging.logger import pipeline_logger
                pipeline_logger.debug(f"Turn {event.turn_id} submitted: user_input={last_user_msg[:50]}, assistant_response={response[:50]}")
        else:
            # 自动任务（follow-up / tag / title）：不进入记忆管道，只记录简要日志
            from infrastructure.logging.logger import pipeline_logger
            follow_ups = ""
            try:
                import json
                parsed = json.loads(response) if response.startswith("{") else {}
                if "follow_ups" in parsed:
                    follow_ups = " | ".join(parsed["follow_ups"][:3])
            except Exception:
                pass
            pipeline_logger.info(f"Auto task completed. Follow-ups: [{follow_ups}]")

        msg_count = self.sessions.get_message_count(session_id)
        if msg_count > 0 and msg_count % (Config.SUMMARY_INTERVAL * 2) == 0:
            # [S0-13] 条件性摘要生成
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
                "content": Config.SUMMARY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": Config.SUMMARY_USER_PROMPT_TEMPLATE.format(history_text=history_text),
            },
        ]

        try:
            llm = LLMFactory.get(model=self._model_override)
            summary = llm.chat(prompt)
            pipeline_logger.info(f"Summary generated: {summary}")
            embedding = EmbeddingService.embed(summary)
            self.qdrant.save_summary(summary, embedding)
        except Exception as e:
            pipeline_logger.error(f"[ERROR] Summary generation failed: {e}")
            print(f"[WARN] Summary generation failed: {e}")
