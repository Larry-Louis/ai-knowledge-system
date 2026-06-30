import time
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.chat import router as chat_router
from infrastructure.config.config import Config
from infrastructure.runtime.state import set_active_doc_ids, get_active_doc_ids, get_active_role, set_active_role, get_core_write_mode


from infrastructure.embedding.embedding import EmbeddingService


app = FastAPI(title="RAG API - World Memory System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


class ActiveDocsRequest(BaseModel):
    doc_ids: List[str]


class RoleRequest(BaseModel):
    role: str


@app.get("/documents/active")
def get_active_docs():
    return {"active_doc_ids": list(get_active_doc_ids())}


@app.post("/documents/active")
def set_active_docs(req: ActiveDocsRequest):
    set_active_doc_ids(req.doc_ids)
    return {"active_doc_ids": list(get_active_doc_ids()), "count": len(get_active_doc_ids())}


@app.get("/role")
def get_role():
    return {
        "role": get_active_role(),
        "core_write_mode": get_core_write_mode(),
        "available_layers": Config.MEMORY_LAYERS,
    }


@app.post("/role")
def set_role(req: RoleRequest):
    try:
        set_active_role(req.role)
        return {"role": get_active_role(), "message": f"已切换到「{req.role}」层"}
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(400, str(e))


@app.post("/memories/cleanup")
def cleanup_memories():
    """Delete auto-task memories from Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from infrastructure.vector.qdrant_store import QdrantStore
    from application.memory_service import _is_auto_task
    qs = QdrantStore()
    pts = qs.client.scroll(collection_name='memories', limit=500, with_payload=True)[0]
    to_delete = [p.id for p in pts if _is_auto_task(p.payload.get("content", ""))]
    if to_delete:
        qs.client.delete(collection_name='memories', points_selector=to_delete)
    return {"deleted": len(to_delete), "message": f"已清理 {len(to_delete)} 条自动任务记忆"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/warmup")
def warmup():
    """Preload embedding model (nomic-embed-text) into Ollama memory."""
    start = time.time()
    results = {}

    try:
        EmbeddingService.embed("warmup")
        results["embedding"] = "ok"
    except Exception as e:
        results["embedding"] = str(e)

    elapsed = time.time() - start
    return {"warmup": results, "elapsed_seconds": round(elapsed, 1)}


@app.post("/embed")
def embed_text(text: str):
    """Embed text via Ollama (proxy for other services)."""
    try:
        vector = EmbeddingService.embed(text)
        return {"embedding": vector}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(500, str(e))


@app.get("/v1/models")
def list_models():
    model_id = {
        "ollama": Config.OLLAMA_MODEL,
        "deepseek": Config.DEEPSEEK_MODEL,
        "openai": Config.OPENAI_MODEL,
    }.get(Config.LLM_PROVIDER, "unknown")

    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "user",
            }
        ],
    }
from application.memory_pipeline_service import start_pipeline
@app.on_event("startup")
def startup_event():
    start_pipeline()