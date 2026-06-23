import os
import uuid
import time

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from models.schema import ChatRequest, ChatResponse
from services.parser import parse_document, extract_pdf_text, validate_text
from services.indexer import DocumentIndexer
from services.embedding import embed
from services.llm import chat as llm_chat
import httpx

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
- 我会从文档中检索相关段落给你作为参考，每段都标注了段落编号
- 段落编号按顺序递增，编号越小越靠前
- 如果用户问"第一次""开始""最初"这类时序问题，注意利用段落编号顺序判断先后
- 基于检索到的内容，用自然对话的方式回答用户
- 回答要像在聊天一样自然，不要输出格式化报告
- 如果检索到的信息不够，如实告知用户"""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload")
async def upload_document(file: UploadFile):
    """
    上传文档（.txt 或 .pdf），解析为章节，向量化后索引到 Qdrant

    主要工作流：
    1. 确定文件类型（txt 或 pdf）
    2. 提取文本内容（PDF 使用 PyMuPDF，TXT 支持 UTF-8/GBK）
    3. 验证文本有效性
    4. 解析为顺序编号的块（每块 ≤ 1000 字符）
    5. 为每个块生成向量嵌入
    6. 将块索引到 Qdrant 的 documents 集合
    7. 返回文档 ID、标题、块数等信息
    """
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

    # Parse into sequentially numbered chunks (each ≤ 1000 chars)
    chunks = parse_document(text)
    if not chunks:
        raise HTTPException(400, "未能解析出任何有效内容")

    # Generate document ID
    doc_id = str(uuid.uuid4())
    doc_title = file.filename.rsplit(".", 1)[0]

    # Embed each chunk
    embeddings = []
    for i, ch in enumerate(chunks):
        try:
            emb = embed(ch["content"][:2000])
        except Exception as e:
            raise HTTPException(500, f"第{ch['chapter']}章第{ch['chunk']}块向量化失败: {e}")
        embeddings.append(emb)

    # Index into Qdrant
    count = indexer.index_chapters(doc_id, doc_title, chunks, embeddings)

    return {
        "document_id": doc_id,
        "title": doc_title,
        "total_chunks": len(chunks),
        "indexed": count,
    }


@app.get("/documents")
def list_documents():
    """List all uploaded documents."""
    docs = indexer.list_documents()
    return {"documents": docs}


@app.post("/documents/{doc_id}/chat", response_model=ChatResponse)
def chat_with_document(doc_id: str, req: ChatRequest):
    """
    与文档对话：AI 自动搜索所有章节的相关内容并生成回答

    主要工作流：
    1. 将用户消息向量化
    2. 在文档中搜索语义相关的块（top_k=8）
    3. 按段落编号排序以保持时序顺序
    4. 构建上下文（最多 6000 字符）
    5. 调用 LLM 生成回答
    6. 去重来源段落编号
    7. 返回回答和来源列表
    """
    # Embed user message
    query_embedding = embed(req.message)

    # Search across the entire document for relevant content
    all_chunks = indexer.search_all(doc_id, query_embedding, top_k=8)

    # Build context from retrieved chunks (sorted by paragraph number for sequence)
    all_chunks.sort(key=lambda x: x.get("chapter", 0))
    context = ""
    sources = []
    for c in all_chunks:
        if len(context) >= 6000:
            break
        label = f"[第{c['chapter']}段]"
        chunk_text = (c.get("content") or "")[:1200]
        context += f"{label}\n{chunk_text}\n\n"
        sources.append(f"第{c['chapter']}段")

    user_prompt = f"""以下是文档中与你问题相关的段落：

{context[:30000]}

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
