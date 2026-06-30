"""Application-level gateway for LLM client resolution.

Keeps application services decoupled from infrastructure factory details.
"""

from infrastructure.llm.llm_client import LLMFactory


def get_llm(*, model: str | None = None, role: str | None = None):
    """Return an LLM client based on app-level role/model policy."""
    if not model and role in {"story", "docreader"}:
        return LLMFactory.get(provider="deepseek", model="deepseek-v4-flash")
    return LLMFactory.get(model=model)


__all__ = ["get_llm"]