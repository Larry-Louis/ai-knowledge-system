"""Domain entities for document reader."""

from dataclasses import dataclass


@dataclass
class DocumentChunk:
    chapter: int
    title: str
    content: str
