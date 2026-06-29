"""Prompt builder entrypoint.

Kept as a thin alias to preserve a clear application-layer boundary.
"""

from prompts.prompt import build_prompt

__all__ = ["build_prompt"]
