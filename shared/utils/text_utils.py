"""Shared text utilities."""


def clamp_text(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    return text[:max_len]
