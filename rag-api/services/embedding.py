import httpx
from core.config import Config


class EmbeddingService:
    @classmethod
    def embed(cls, text: str) -> list[float]:
        payload = {"model": Config.OLLAMA_EMBEDDING_MODEL, "input": text}
        with httpx.Client(timeout=600) as client:
            resp = client.post(
                f"{Config.OLLAMA_BASE_URL}/api/embed", json=payload
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]
