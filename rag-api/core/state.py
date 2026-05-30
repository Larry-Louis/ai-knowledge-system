"""Shared mutable state for the rag-api application."""
from typing import Set

_active_doc_ids: Set[str] = set()
_active_role: str = "general"


def get_active_doc_ids() -> Set[str]:
    return _active_doc_ids


def set_active_doc_ids(ids: list[str]):
    _active_doc_ids.clear()
    _active_doc_ids.update(ids)


def clear_active_doc_ids():
    _active_doc_ids.clear()


def get_active_role() -> str:
    return _active_role


def set_active_role(role: str):
    global _active_role
    from core.config import Config
    allowed = set(Config.MEMORY_LAYERS.keys()) | {Config.CORE_LAYER}
    if role not in allowed:
        raise ValueError(f"未知记忆层: {role}，可用层: {', '.join(sorted(allowed))}")
    _active_role = role
