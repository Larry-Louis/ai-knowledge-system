import os
import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")


def embed(text: str) -> list[float]:
    """Embed text using Ollama embedding API (via host on Windows)."""
    payload = {"model": OLLAMA_EMBEDDING_MODEL, "input": text}
    with httpx.Client(timeout=900) as client:
        resp = client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]
