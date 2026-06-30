from collections import defaultdict, deque
from infrastructure.config.config import Config


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, deque[dict]] = defaultdict(
            lambda: deque(maxlen=Config.SHORT_TERM_SIZE * 2)
        )

    def add_message(self, session_id: str, role: str, content: str):
        """
        [S0-9] 添加消息到会话存储

        主要工作流：
        1. 将消息（角色和内容）追加到指定会话的 deque 中
        2. deque 最大长度由 Config.SHORT_TERM_SIZE * 2 控制
        """
        self._sessions[session_id].append({"role": role, "content": content})

    def get_recent(self, session_id: str, n: int = None) -> list[dict]:
        """
        [S0-13] 获取最近的 n 条消息

        用于摘要生成时获取最近的对话历史
        """
        if n is None:
            n = Config.SHORT_TERM_SIZE
        messages = list(self._sessions.get(session_id, []))
        return messages[-n:]

    def get_all(self, session_id: str) -> list[dict]:
        """
        获取指定会话的所有消息
        """
        return list(self._sessions.get(session_id, []))

    def get_message_count(self, session_id: str) -> int:
        """
        [S0-13] 获取指定会话的消息数量

        用于判断是否需要触发摘要生成
        """
        return len(self._sessions.get(session_id, []))
