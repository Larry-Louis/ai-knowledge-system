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

    # 测试模式开关，可以通过环境变量开启
    TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
    SYSTEM_VERSION = "2.0.4-RC"
    
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个长期世界构建AI（小说/游戏设计助手）。你必须保证设定一致性，维护世界观、角色和剧情的连贯性。每次回答都要基于已有的世界观信息，并自然地延续设定。")
    SUMMARY_SYSTEM_PROMPT = os.getenv("SUMMARY_SYSTEM_PROMPT", "你是世界观摘要生成器。基于对话历史提取关键设定、角色、事件，生成简洁的世界观摘要。")
    SUMMARY_USER_PROMPT_TEMPLATE = os.getenv("SUMMARY_USER_PROMPT_TEMPLATE", "基于以下对话内容，生成世界观摘要（包含核心设定、重要角色、关键事件、规则）：\n\n{history_text}")
    
    # 超时配置
    SLM_VALIDATION_TIMEOUT = int(os.getenv("SLM_VALIDATION_TIMEOUT", "120"))
