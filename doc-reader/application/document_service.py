"""Document application service.

Keeps business orchestration out of API handlers.
"""

import os
import uuid
import tempfile

import httpx
from fastapi import HTTPException, UploadFile

from models.api_schema import ChatResponse
from infrastructure.embedding.embedding import embed
from infrastructure.index.indexer import DocumentIndexer
from infrastructure.llm.llm_client import chat as llm_chat
from infrastructure.parser.parser import parse_document, extract_pdf_text, validate_text


RAG_API_BASE = os.getenv("RAG_API_URL", "http://rag-api:8000")

CHAT_SYSTEM_PROMPT = """你是一个文档智能问答助手。你可以访问一篇文档的全部内容。

你的工作方式：
- 我会从文档中检索相关段落给你作为参考，每段都标注了段落编号
- 段落编号按顺序递增，编号越小越靠前
- 如果用户问"第一次""开始""最初"这类时序问题，注意利用段落编号顺序判断先后
- 基于检索到的内容，用自然对话的方式回答用户
- 回答要像在聊天一样自然，不要输出格式化报告
- 如果检索到的信息不够，如实告知用户"""


class DocumentService:
    def __init__(self):
        self.indexer = DocumentIndexer()

    def get_active_docs(self) -> dict:
        resp = httpx.get(f"{RAG_API_BASE}/documents/active", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def set_active_docs(self, doc_ids: list[str]) -> dict:
        resp = httpx.post(
            f"{RAG_API_BASE}/documents/active",
            json={"doc_ids": doc_ids},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    async def upload_document(self, file: UploadFile) -> dict:
        fname = (file.filename or "").lower()
        is_pdf = fname.endswith(".pdf")
        if not (fname.endswith(".txt") or is_pdf):
            raise HTTPException(400, "仅支持 .txt 和 .pdf 文件")

        raw = await file.read()

        if is_pdf:
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
                except UnicodeDecodeError as exc:
                    raise HTTPException(400, "文件编码不支持，请使用 UTF-8 或 GBK") from exc

        valid, err = validate_text(text)
        if not valid:
            raise HTTPException(400, err)

        chunks = parse_document(text)
        if not chunks:
            raise HTTPException(400, "未能解析出任何有效内容")

        doc_id = str(uuid.uuid4())
        doc_title = (file.filename or "untitled").rsplit(".", 1)[0]

        embeddings: list[list[float]] = []
        for ch in chunks:
            try:
                emb = embed(ch["content"][:2000])
            except Exception as exc:
                raise HTTPException(
                    500,
                    f"第{ch['chapter']}章第{ch['chunk']}块向量化失败: {exc}",
                ) from exc
            embeddings.append(emb)

        count = self.indexer.index_chapters(doc_id, doc_title, chunks, embeddings)
        return {
            "document_id": doc_id,
            "title": doc_title,
            "total_chunks": len(chunks),
            "indexed": count,
        }

    def list_documents(self) -> dict:
        return {"documents": self.indexer.list_documents()}

    def chat_with_document(self, doc_id: str, message: str) -> ChatResponse:
        query_embedding = embed(message)
        all_chunks = self.indexer.search_all(doc_id, query_embedding, top_k=8)

        all_chunks.sort(key=lambda x: x.get("chapter", 0))
        context = ""
        sources: list[str] = []
        for chunk in all_chunks:
            if len(context) >= 6000:
                break
            label = f"[第{chunk['chapter']}段]"
            chunk_text = (chunk.get("content") or "")[:1200]
            context += f"{label}\n{chunk_text}\n\n"
            sources.append(f"第{chunk['chapter']}段")

        user_prompt = f"""以下是文档中与你问题相关的段落：

{context[:30000]}

用户问题: {message}"""

        messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            reply = llm_chat(messages)
        except Exception as exc:
            raise HTTPException(500, f"回答生成失败: {exc}") from exc

        seen = set()
        sources_uniq = []
        for source in sources:
            if source not in seen:
                seen.add(source)
                sources_uniq.append(source)

        return ChatResponse(reply=reply, sources=sources_uniq)

    def delete_document(self, doc_id: str) -> dict:
        self.indexer.delete_document(doc_id)
        return {"status": "deleted", "document_id": doc_id}
