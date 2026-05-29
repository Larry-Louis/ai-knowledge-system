# AI 世界观记忆系统（可运行实现版）

## 目标

实现一个 FastAPI 服务 `rag-api`，提供：

### ✔ OpenAI兼容接口

- `/v1/chat/completions`

用于 OpenWebUI 直接接入

---

### ✔ 三层记忆系统

1. short-term memory（最近对话）
2. long-term memory（Qdrant）
3. world summary memory（压缩世界观）

---

### ✔ 可切换 LLM

支持：

- Ollama（本地 Qwen 3.5 9B）
- DeepSeek API
- OpenAI API

通过 config 切换，不改业务逻辑

---

# 系统架构

```
OpenWebUI
   ↓
/v1/chat/completions (rag-api)
   ↓
Context Builder
   ↓
Memory Layer (Qdrant + session memory)
   ↓
LLM Adapter (Ollama / DeepSeek / OpenAI)
   ↓
Response
```

---

# 目录结构（必须实现）

```
rag-api/
├── app.py
├── api/
│   └── chat.py
├── core/
│   ├── memory.py
│   ├── prompt.py
│   ├── llm.py
│   ├── config.py
│   └── router.py
├── services/
│   ├── qdrant_store.py
│   ├── embedding.py
│   └── session_store.py
└── models/
    └── schema.py
```

---

# API 规范（必须实现）

## POST /v1/chat/completions

### Request

```
{
  "model": "any",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "session_id": "abc123"
}
```

---

### Response

```
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      }
    }
  ]
}
```

---

# 核心逻辑流程（必须实现）

## 1. 请求入口

```
messages + session_id
```

---

## 2. memory retrieval（关键）

### step1：存储当前 user message

```
save_to_session(session_id, role="user", content=...)
```

---

### step2：向量检索历史

```
related_memories = qdrant.search(
    query_embedding=user_message,
    top_k=8,
    filter=session_id
)
```

---

### step3：最近对话（short-term）

```
recent_messages = get_last_n_messages(session_id, n=20)
```

---

### step4：world summary

```
world_summary = load_summary(session_id)
```

---

## 3. prompt builder（必须统一）

```
final_prompt = [
    SYSTEM_PROMPT,
    world_summary,
    related_memories,
    recent_messages,
    current_user_message
]
```

---

## 4. LLM调用（抽象层）

```
llm = LLMFactory.get(provider=config.LLM_PROVIDER)

response = llm.chat(messages=final_prompt)
```

---

# LLM Adapter（必须实现）

## interface

```
class LLMClient:
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError
```

---

## Ollama实现

```
class OllamaClient(LLMClient):
    model = "qwen2.5:9b"

    def chat(self, messages):
        # http://localhost:11434/api/chat
```

---

## DeepSeek实现

```
class DeepSeekClient(LLMClient):
    api_key = os.getenv("DEEPSEEK_API_KEY")

    def chat(self, messages):
        # OpenAI-compatible endpoint
```

---

## OpenAI实现

```
class OpenAIClient(LLMClient):
    def chat(self, messages):
        # OpenAI API call
```

---

# Memory系统（Qdrant）

## 存储结构

```
{
  "id": uuid,
  "session_id": "...",
  "role": "user|assistant",
  "content": "...",
  "embedding": vector,
  "timestamp": ...
}
```

---

## 必须实现功能

- upsert memory
- search memory by embedding
- filter by session_id

---

# Embedding模型

默认：

```
BAAI/bge-base-zh-v1.5
```

---

# Session Store（必须实现）

```
session_id -> list[messages]
```

用于：

- 最近20轮对话
- prompt拼接

---

# Prompt规则（非常重要）

必须保证：

### SYSTEM固定：

```
你是一个长期世界构建AI（小说/游戏设计助手）
你必须保证设定一致性
```

---

### 每次输入必须包含：

- 整体 summary
- 相关 memory
- 最近对话
- 当前问题

---

# OpenWebUI对接要求

必须保证：

```
Base URL:
http://rag-api:8000/v1

Model:
anything
```

---

# 配置文件（必须实现）

```
class Config:
    LLM_PROVIDER = "ollama"  # ollama | deepseek | openai

    OLLAMA_MODEL = "qwen2.5:9b"

    QDRANT_URL = "http://qdrant:6333"
```

---

# 必须修复你当前代码的问题

## ❌ 删除

```
VectorStoreIndex([])
```

---

## ❌ 不允许直接调用 embed model resolve OpenAI（你之前报错）

必须：

- 要么明确 embedding model
- 要么完全走 local embedding

---

# 最终效果

实现后系统能力：

## ✔ 长期记忆

不会忘世界观

## ✔ session连续性

能持续构建剧情

## ✔ 多模型切换

一行 config 切换 LLM

## ✔ OpenWebUI可用

标准 OpenAI API

---

# 一句话总结给 Claude

> 这是一个“OpenAI兼容 API + Qdrant长期记忆 + 可切换LLM + 世界观持续构建系统”，需要实现完整 memory + prompt orchestration + LLM adapter layer。