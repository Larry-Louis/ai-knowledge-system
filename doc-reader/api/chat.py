"""Doc-reader API routes."""

from pydantic import BaseModel
from fastapi import APIRouter, UploadFile

from models.api_schema import ChatRequest, ChatResponse
from application.document_service import DocumentService


router = APIRouter()
service = DocumentService()


class ActiveDocsRequest(BaseModel):
	doc_ids: list[str]


@router.get("/rag-api/documents/active")
def proxy_get_active_docs():
	return service.get_active_docs()


@router.post("/rag-api/documents/active")
def proxy_set_active_docs(req: ActiveDocsRequest):
	return service.set_active_docs(req.doc_ids)


@router.post("/documents/upload")
async def upload_document(file: UploadFile):
	return await service.upload_document(file)


@router.get("/documents")
def list_documents():
	return service.list_documents()


@router.post("/documents/{doc_id}/chat", response_model=ChatResponse)
def chat_with_document(doc_id: str, req: ChatRequest):
	return service.chat_with_document(doc_id=doc_id, message=req.message)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
	return service.delete_document(doc_id)
