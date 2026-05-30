import re
import os


def split_by_chapter(text: str) -> list[dict]:
    """Split text into chapters. Supports Chinese and English chapter markers."""
    # Patterns: 第一章, 第1章, 第 一 章,  Chapter 1, CHAPTER 1, Chapter One, etc.
    pattern = (
        r'(第\s*[一二三四五六七八九十百千\d]+\s*[章节部篇]'
        r'|Chapter\s+\d+'
        r'|CHAPTER\s+\d+)'
    )
    splits = re.split(pattern, text)

    # Clean up: remove empty parts before first chapter
    if splits and not splits[0].strip():
        splits = splits[1:]

    # re.split returns [title1, content1, title2, content2, ...]
    chapters = []
    for i in range(0, len(splits) - 1, 2):
        title = splits[i].strip()
        content = splits[i + 1].strip() if i + 1 < len(splits) else ""
        chapters.append({
            "chapter": len(chapters) + 1,
            "title": title,
            "content": content,
        })

    # If no chapters found, treat entire text as one chapter
    if not chapters:
        chapters.append({
            "chapter": 1,
            "title": "全文",
            "content": text.strip(),
        })

    return chapters


def validate_text(text: str) -> tuple[bool, str]:
    """Validate the uploaded text content."""
    if not text or not text.strip():
        return False, "文件内容为空"
    if len(text) < 10:
        return False, "文件内容太短（至少10个字符）"
    return True, ""
