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


class QueryRequest(BaseModel):
    chapter: int
    question: Optional[str] = ""


class QueryResponse(BaseModel):
    document_id: str
    chapter: int
    chapter_title: str
    chapter_content: str
    analysis: str
