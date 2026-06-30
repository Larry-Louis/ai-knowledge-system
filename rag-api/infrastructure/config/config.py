import os


class Config:
    # Runtime / diagnostics
    TEST_MODE = os.getenv("TEST_MODE", "0").lower() in ("1", "true", "yes", "on")
    SYSTEM_VERSION = os.getenv("SYSTEM_VERSION", "v1")

    # Provider routing
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

    # Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    # OpenAI-compatible
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Memory / retrieval
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
    QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
    QDRANT_MEMORY_COLLECTION = os.getenv("QDRANT_MEMORY_COLLECTION", "memories")
    QDRANT_INSIGHT_COLLECTION = os.getenv("QDRANT_INSIGHT_COLLECTION", "insights")
    MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "8"))
    INSIGHT_TOP_K = int(os.getenv("INSIGHT_TOP_K", "6"))
    SHORT_TERM_SIZE = int(os.getenv("SHORT_TERM_SIZE", "20"))
    SUMMARY_INTERVAL = int(os.getenv("SUMMARY_INTERVAL", "6"))

    # Prompting / policies
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个可靠、准确、简洁的中文助理。")
    SUMMARY_SYSTEM_PROMPT = os.getenv(
        "SUMMARY_SYSTEM_PROMPT",
        "请将最近对话总结为短摘要，保留用户偏好、任务进展与关键事实。",
    )
    SUMMARY_USER_PROMPT_TEMPLATE = os.getenv(
        "SUMMARY_USER_PROMPT_TEMPLATE",
        "请基于以下对话生成摘要：\n\n{history_text}",
    )
    SLM_VALIDATION_TIMEOUT = int(os.getenv("SLM_VALIDATION_TIMEOUT", "45"))

    # Layering / role routing
    CORE_LAYER = os.getenv("CORE_LAYER", "core")
    MEMORY_LAYERS = {
        "general": "通用记忆层",
        "story": "故事创作层",
        "docreader": "文档阅读层",
        "core": "核心记忆层",
    }
    AVAILABLE_MODELS = [
        "deepseek-v4-flash",
        "deepseek-r1:8b",
        "qwen3.5:9b",
        "gpt-4o-mini",
    ]

    # Core-write triggers
    CORE_TRIGGERS = [
        "记住：",
        "写入核心：",
        "核心记录：",
    ]
