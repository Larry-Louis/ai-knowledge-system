"""Shared memory contracts between services."""

from dataclasses import dataclass


@dataclass
class MemoryContract:
    session_id: str
    turn_id: str
    content: str
