"""Shared mutable state for the rag-api application."""
from typing import Set

_active_doc_ids: Set[str] = set()


def get_active_doc_ids() -> Set[str]:
    return _active_doc_ids


def set_active_doc_ids(ids: list[str]):
    _active_doc_ids.clear()
    _active_doc_ids.update(ids)


def clear_active_doc_ids():
    _active_doc_ids.clear()
