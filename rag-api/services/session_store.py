from collections import defaultdict, deque
from core.config import Config


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, deque[dict]] = defaultdict(
            lambda: deque(maxlen=Config.SHORT_TERM_SIZE * 2)
        )

    def add_message(self, session_id: str, role: str, content: str):
        self._sessions[session_id].append({"role": role, "content": content})

    def get_recent(self, session_id: str, n: int = None) -> list[dict]:
        if n is None:
            n = Config.SHORT_TERM_SIZE
        messages = list(self._sessions.get(session_id, []))
        return messages[-n:]

    def get_all(self, session_id: str) -> list[dict]:
        return list(self._sessions.get(session_id, []))

    def get_message_count(self, session_id: str) -> int:
        return len(self._sessions.get(session_id, []))
