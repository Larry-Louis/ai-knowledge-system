"""Shared schema definitions for cross-service contracts."""

from dataclasses import dataclass


@dataclass
class SharedMessage:
    role: str
    content: str
