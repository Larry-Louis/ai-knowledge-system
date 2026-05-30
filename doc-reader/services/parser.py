import re
import os


def split_by_chapter(text: str) -> list[dict]:
    """Split text into chapters. Supports Chinese and English chapter markers."""
    # Patterns: 第一章, 第1章, 第 一 章,  Chapter 1, CHAPTER 1, Chapter One, etc.
    # Only match at start of line (after newline or at text start)
    pattern = (
        r'(?:^|\n)\s*(第\s*[一二三四五六七八九十百千\d]+\s*[章节部篇]'
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


def chunk_by_paragraphs(text: str, max_chars: int = 1000) -> list[str]:
    """Split text into chunks by paragraph boundaries, each ≤ max_chars."""
    # Split into paragraphs (by double or single newlines)
    paras = [p.strip() for p in re.split(r'\n\s*\n|\n(?!\n)', text) if p.strip()]
    if not paras:
        return [text[:max_chars]] if text else []

    chunks = []
    current = ""
    for p in paras:
        # If adding this paragraph would exceed max_chars, start a new chunk
        if current and len(current) + len(p) + 1 > max_chars:
            chunks.append(current.strip())
            current = p
        elif not current:
            current = p
        else:
            current += "\n" + p

        # If a single paragraph exceeds max_chars, split it mid-paragraph
        while len(current) >= max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars:].strip()

    if current.strip():
        chunks.append(current.strip())

    return chunks


def flatten_chunks(chapters: list[dict], max_chars: int = 1000) -> list[dict]:
    """Take chapter list and split each chapter into paragraph-based chunks."""
    result = []
    for ch in chapters:
        sub_chunks = chunk_by_paragraphs(ch["content"], max_chars)
        for i, content in enumerate(sub_chunks):
            result.append({
                "chapter": ch["chapter"],
                "title": ch["title"],
                "chunk": i + 1,
                "chunks_total": len(sub_chunks),
                "content": content,
            })
    return result


def extract_pdf_text(filepath: str) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    import fitz
    doc = fitz.open(filepath)
    text_parts = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            text_parts.append(text)
    doc.close()
    return "\n\n".join(text_parts)


def validate_text(text: str) -> tuple[bool, str]:
    """Validate the uploaded text content."""
    if not text or not text.strip():
        return False, "文件内容为空"
    if len(text) < 10:
        return False, "文件内容太短（至少10个字符）"
    return True, ""
