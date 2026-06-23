import httpx
from core.config import Config


class EmbeddingService:
    @classmethod
    def embed(cls, text: str) -> list[float]:
        """
        [S0-3] 文本向量化：使用 Ollama 嵌入 API 将文本转换为向量

        主要工作流：
        1. 验证输入文本非空
        2. 调用 Ollama /api/embed 端点
        3. 返回第一个嵌入向量
        """
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
