from sentence_transformers import SentenceTransformer
from core.config import Config


class EmbeddingService:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            cls._model = SentenceTransformer(Config.EMBEDDING_MODEL)
        return cls._model

    @classmethod
    def embed(cls, text: str) -> list[float]:
        model = cls.get_model()
        return model.encode(text).tolist()

    @classmethod
    def embed_batch(cls, texts: list[str]) -> list[list[float]]:
        model = cls.get_model()
        return model.encode(texts).tolist()
