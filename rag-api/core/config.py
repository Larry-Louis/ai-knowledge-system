import os

class Config:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:latest")

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
    QDRANT_MEMORY_COLLECTION = os.getenv("QDRANT_MEMORY_COLLECTION", "memories")

    OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

    SHORT_TERM_SIZE = int(os.getenv("SHORT_TERM_SIZE", "20"))
    MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "8"))
    SUMMARY_INTERVAL = int(os.getenv("SUMMARY_INTERVAL", "30"))

    MEMORY_LAYERS = {
        "general": "默认对话",
        "story": "故事创作与世界观设计",
        "docreader": "文档分析与阅读",
    }
    
    # 新增的路由配置
    AVAILABLE_MODELS = ["deepseek-r1:8b", "deepseek-v4-flash", "deepseek-r1:latest"]
    COMPLEX_LAYERS = ["story", "docreader"]

    CORE_LAYER = "core"
    CORE_TRIGGERS = ["记住：", "要记得：", "写入核心："]

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
    SYSTEM_VERSION = "2.0.4-RC"
