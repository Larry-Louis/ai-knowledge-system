import uuid
import time

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models.schema import ChatRequest, ChatResponse
from services.parser import split_by_chapter, extract_pdf_text, validate_text
from services.indexer import DocumentIndexer
from services.embedding import embed
from services.llm import chat as llm_chat

RAG_API_BASE = os.getenv("RAG_API_URL", "http://rag-api:8000")

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


# Proxy: get active mounted docs from rag-api
@app.get("/rag-api/documents/active")
def proxy_get_active_docs():
    r = httpx.get(f"{RAG_API_BASE}/documents/active", timeout=5)
    return r.json()


# Proxy: set active mounted docs on rag-api
class ActiveDocsRequest(BaseModel):
    doc_ids: list[str]

@app.post("/rag-api/documents/active")
def proxy_set_active_docs(req: ActiveDocsRequest):
    r = httpx.post(f"{RAG_API_BASE}/documents/active", json={"doc_ids": req.doc_ids}, timeout=5)
    return r.json()


CHAT_SYSTEM_PROMPT = """你是一个文档智能问答助手。你可以访问一篇文档的全部内容。

你的工作方式：
- 当用户问你关于文档的问题时，我会从全文中检索相关段落给你作为参考
- 基于检索到的内容，用自然对话的方式回答用户
- 如果用户提到某个人物/事件，尽可能关联它在文档其他部分的发展和前后关系
- 回答要像在聊天一样自然，不要输出格式化报告
- 如果检索到的信息不够，如实告知用户"""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload")
async def upload_document(file: UploadFile):
    """Upload a document (.txt or .pdf), parse into chapters, and index into Qdrant."""
    # Determine file type
    fname = file.filename.lower()
    is_pdf = fname.endswith(".pdf")
    if not (fname.endswith(".txt") or is_pdf):
        raise HTTPException(400, "仅支持 .txt 和 .pdf 文件")

    raw = await file.read()

    # Extract text
    if is_pdf:
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        try:
            tmp.write(raw)
            tmp.close()
            text = extract_pdf_text(tmp.name)
        finally:
            os.unlink(tmp.name)
        if not text.strip():
            raise HTTPException(400, "PDF 文件无法提取出文本内容")
    else:
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


@app.post("/documents/{doc_id}/chat", response_model=ChatResponse)
def chat_with_document(doc_id: str, req: ChatRequest):
    """Chat with a document. AI automatically searches across all chapters for relevant context."""
    # Embed user message
    query_embedding = embed(req.message)

    # Search across the entire document for relevant content
    all_chunks = indexer.search_all(doc_id, query_embedding, top_k=8)

    # Build context from retrieved chunks
    context = ""
    sources = []
    for c in all_chunks:
        label = f"[第{c['chapter']}章 {c['title']}]"
        context += f"{label}\n{c['content'][:1200]}\n\n"
        sources.append(f"第{c['chapter']}章")

    user_prompt = f"""以下是文档中与你问题相关的段落：

{context}

用户问题: {req.message}"""

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        reply = llm_chat(messages)
    except Exception as e:
        raise HTTPException(500, f"回答生成失败: {e}")

    # Deduplicate source chapter names
    seen = set()
    sources_uniq = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            sources_uniq.append(s)

    return ChatResponse(reply=reply, sources=sources_uniq)


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and all its chapters."""
    indexer.delete_document(doc_id)
    return {"status": "deleted", "document_id": doc_id}
