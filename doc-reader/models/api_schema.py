from pydantic import BaseModel
from typing import Optional, List


class ChapterInfo(BaseModel):
    chapter: int
    title: str
    content: str


class DocumentInfo(BaseModel):
    id: str
    title: str
    total_chapters: int
    chapters: List[ChapterInfo]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    sources: List[str] = []
