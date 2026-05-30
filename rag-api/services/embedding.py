import httpx
from core.config import Config


class EmbeddingService:
    @classmethod
    def embed(cls, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("不能向量化空文本")
        payload = {"model": Config.OLLAMA_EMBEDDING_MODEL, "input": text}
        with httpx.Client(timeout=900) as client:
            resp = client.post(
                f"{Config.OLLAMA_BASE_URL}/api/embed", json=payload
            )
            if resp.status_code != 200:
                detail = resp.text[:300]
                raise Exception(f"Ollama {resp.status_code}: {detail}")
            return resp.json()["embeddings"][0]
