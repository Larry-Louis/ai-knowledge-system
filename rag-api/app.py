from fastapi import FastAPI
from pydantic import BaseModel

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    SimpleDirectoryReader,
)

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import StorageContext
from llama_index.core import Settings
from qdrant_client import QdrantClient

import os

Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-base-zh-v1.5"
)

app = FastAPI()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
client = QdrantClient(url=QDRANT_URL)

vector_store = QdrantVectorStore(
    client=client,
    collection_name="docs"
)

storage_context = StorageContext.from_defaults(
    vector_store=vector_store
)

index = VectorStoreIndex([], storage_context=storage_context)


class Query(BaseModel):
    question: str


@app.post("/query")
def query(q: Query):
    engine = index.as_query_engine()
    return {
        "answer": str(engine.query(q.question))
    }