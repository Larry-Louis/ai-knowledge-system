import uuid
import time

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models.schema import QueryRequest, QueryResponse
from services.parser import split_by_chapter, validate_text
from services.indexer import DocumentIndexer
from services.embedding import embed
from services.llm import chat as llm_chat

app = FastAPI(title="Doc Reader - 长文档智能阅读")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

indexer = DocumentIndexer()

# Serve static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


SYSTEM_PROMPT = """你是一个文档分析AI助手。用户会给你一篇文档中某个章节的内容，以及从文档其他部分检索到的相关内容。

你的任务是：
1. 先完整讲述该章节的核心内容
2. 然后分析这个章节中提到的人物、事件、设定，与文档其他部分的关联：
   - 这些人/事在之前的章节中有什么铺垫
   - 这些人/事在之后的章节中有什么发展或结果
   - 这个章节埋下了哪些伏笔
   - 这个章节呼应了之前的哪些内容

请用中文回答，条理清晰。"""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload")
async def upload_document(file: UploadFile):
    """Upload a text document, parse into chapters, and index into Qdrant."""
    # Validate file type
    if not file.filename.endswith(".txt"):
        raise HTTPException(400, "仅支持 .txt 文件")

    # Read content
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            raise HTTPException(400, "文件编码不支持，请使用 UTF-8 或 GBK")

    # Validate
    valid, err = validate_text(text)
    if not valid:
        raise HTTPException(400, err)

    # Split into chapters
    chapters = split_by_chapter(text)
    if not chapters:
        raise HTTPException(400, "未能解析出任何章节内容")

    # Generate document ID
    doc_id = str(uuid.uuid4())
    doc_title = file.filename.rsplit(".", 1)[0]

    # Embed each chapter
    embeddings = []
    for i, ch in enumerate(chapters):
        try:
            emb = embed(ch["content"][:2000])  # embed first 2000 chars
        except Exception as e:
            raise HTTPException(500, f"第{ch['chapter']}章向量化失败: {e}")
        embeddings.append(emb)

    # Index into Qdrant
    count = indexer.index_chapters(doc_id, doc_title, chapters, embeddings)

    return {
        "document_id": doc_id,
        "title": doc_title,
        "total_chapters": len(chapters),
        "indexed": count,
    }


@app.get("/documents")
def list_documents():
    """List all uploaded documents."""
    docs = indexer.list_documents()
    return {"documents": docs}


@app.post("/documents/{doc_id}/query", response_model=QueryResponse)
def query_document(doc_id: str, req: QueryRequest):
    """Query a specific chapter with cross-chapter analysis."""
    # Get the chapter
    chapter = indexer.get_chapter(doc_id, req.chapter)
    if not chapter:
        raise HTTPException(404, f"文档中未找到第 {req.chapter} 章")

    # Search related chapters
    chapter_embedding = embed(chapter["content"][:2000])
    related = indexer.search_related(doc_id, req.chapter, chapter_embedding, top_k=6)

    # Build prompt
    related_text = ""
    if related:
        related_text = "\n\n## 文档其他相关段落\n\n"
        for r in related:
            related_text += f"--- 第{r['chapter']}章 {r['title']} ---\n"
            related_text += r["content"][:800] + "\n\n"

    user_prompt = f"""## 当前章节
第{chapter['chapter']}章 {chapter['title']}

{chapter['content']}

{related_text}

## 要求
请先概述第{chapter['chapter']}章的核心内容，然后分析：
1. 本章中的人物在之前或之后章节中的行动和发展
2. 本章中的事件与前后的关联
3. 本章埋下的伏笔或呼应前文的地方
4. 其他值得注意的跨章节关联"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        analysis = llm_chat(messages)
    except Exception as e:
        raise HTTPException(500, f"分析生成失败: {e}")

    return QueryResponse(
        document_id=doc_id,
        chapter=chapter["chapter"],
        chapter_title=chapter["title"],
        chapter_content=chapter["content"][:2000],
        analysis=analysis,
    )


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and all its chapters."""
    indexer.delete_document(doc_id)
    return {"status": "deleted", "document_id": doc_id}
