import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import router as chat_router
from core.config import Config
from services.embedding import EmbeddingService
from core.llm import LLMFactory

app = FastAPI(title="RAG API - World Memory System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/warmup")
def warmup():
    """Preload both embedding and LLM models into Ollama memory."""
    start = time.time()
    results = {}

    try:
        EmbeddingService.embed("warmup")
        results["embedding"] = "ok"
    except Exception as e:
        results["embedding"] = str(e)

    try:
        llm = LLMFactory.get()
        llm.chat([{"role": "user", "content": "warmup"}])
        results["llm"] = "ok"
    except Exception as e:
        results["llm"] = str(e)

    elapsed = time.time() - start
    return {"warmup": results, "elapsed_seconds": round(elapsed, 1)}


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
