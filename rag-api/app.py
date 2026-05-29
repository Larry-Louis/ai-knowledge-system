import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import router as chat_router
from core.config import Config

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


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": f"{Config.LLM_PROVIDER}/{Config.OLLAMA_MODEL}",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "user",
            }
        ],
    }
