"""Application-level prompt builder facade.

This keeps prompt orchestration dependencies flowing through the application
layer while preserving the underlying prompt implementation in prompts/prompt.py.
"""

from typing import Any

from prompts.prompt import build_prompt as _build_prompt_impl


def build_prompt(
	request_messages: list[dict],
	overall_summary: str | None,
	related_memories: list[dict] | None,
	document_chunks: list[dict] | None,
	user_profile: dict[str, Any] | None = None,
) -> list[dict]:
	"""Build the final model prompt with lightweight application-level guards."""
	return _build_prompt_impl(
		request_messages=request_messages,
		overall_summary=overall_summary,
		related_memories=related_memories or [],
		document_chunks=document_chunks or [],
		user_profile=user_profile,
	)


__all__ = ["build_prompt"]
