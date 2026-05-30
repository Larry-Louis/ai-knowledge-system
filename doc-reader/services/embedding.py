import os
import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")


def embed(text: str) -> list[float]:
    """Embed text using Ollama embedding API."""
    if not text or not text.strip():
        raise ValueError("不能向量化空文本")
    payload = {"model": OLLAMA_EMBEDDING_MODEL, "input": text}
    with httpx.Client(timeout=900) as client:
        resp = client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json=payload,
        )
        if resp.status_code != 200:
            detail = resp.text[:300]
            raise Exception(f"Ollama {resp.status_code}: {detail}")
        return resp.json()["embeddings"][0]
