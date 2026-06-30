import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    SimpleDirectoryReader,
)

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import StorageContext
from qdrant_client import QdrantClient

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

client = QdrantClient(url=QDRANT_URL)

vector_store = QdrantVectorStore(
    client=client,
    collection_name="docs"
)

storage_context = StorageContext.from_defaults(
    vector_store=vector_store
)


def ingest(file_path):
    if not file_path.endswith((".pdf", ".txt", ".md")):
        return

    print(f"[INGEST] {file_path}")

    docs = SimpleDirectoryReader(input_files=[file_path]).load_data()

    VectorStoreIndex.from_documents(
        docs,
        storage_context=storage_context
    )


class Handler(FileSystemEventHandler):

    def on_created(self, event):
        if not event.is_directory:
            ingest(event.src_path)


if __name__ == "__main__":
    path = "/docs"
    print("Watching:", path)

    observer = Observer()
    observer.schedule(Handler(), path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()