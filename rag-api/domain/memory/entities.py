"""Domain entities for memory-related concepts."""

from dataclasses import dataclass


@dataclass
class MemoryUnit:
    content: str
    mu_type: str
    mu_tag: str
    layer_type: str
    importance: float
    confidence: float
    store_priority: str
