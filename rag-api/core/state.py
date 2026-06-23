"""Shared mutable state for the rag-api application."""
from typing import Set

_active_doc_ids: Set[str] = set()
_active_role: str = "general"
_core_write_mode: bool = False


def get_active_doc_ids() -> Set[str]:
    """
    [S0-7] 获取当前活跃文档 ID 集合

    用于在构建 RAG 提示时确定需要搜索哪些文档
    """
    return _active_doc_ids


def set_active_doc_ids(ids: list[str]):
    """
    [S0-7] 设置当前活跃文档 ID 集合

    通过 API 端点 /documents/active 调用
    """
    _active_doc_ids.clear()
    _active_doc_ids.update(ids)


def clear_active_doc_ids():
    """
    [S0-7] 清空活跃文档 ID 集合
    """
    _active_doc_ids.clear()


def get_active_role() -> str:
    """
    [S0-1] 获取当前活跃角色层

    用于决定搜索哪些记忆层以及选择 LLM 模型
    """
    return _active_role


def get_core_write_mode() -> bool:
    """
    [S0-7] 获取核心写入模式状态

    当启用时，用户消息中的触发词将触发核心层记忆写入
    """
    return _core_write_mode


def set_core_write_mode(enabled: bool):
    """
    [S0-7] 设置核心写入模式

    当 model 参数为 "core" 时启用
    """
    global _core_write_mode
    _core_write_mode = enabled


def set_active_role(role: str):
    """
    [S0-1] 设置当前活跃角色层

    验证角色是否在允许的层列表中（MEMORY_LAYERS 或 CORE_LAYER）
    """
    global _active_role
    from core.config import Config
    allowed = set(Config.MEMORY_LAYERS.keys()) | {Config.CORE_LAYER}
    if role not in allowed:
        raise ValueError(f"未知记忆层: {role}，可用层: {', '.join(sorted(allowed))}")
    _active_role = role
