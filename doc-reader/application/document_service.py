"""Document application service.

Wraps infrastructure calls and provides a stable seam for API handlers.
"""

from infrastructure.embedding.embedding import embed
from infrastructure.index.indexer import DocumentIndexer
from infrastructure.llm.llm_client import chat
from infrastructure.parser.parser import parse_document, extract_pdf_text, validate_text


__all__ = [
    "embed",
    "chat",
    "DocumentIndexer",
    "parse_document",
    "extract_pdf_text",
    "validate_text",
]
