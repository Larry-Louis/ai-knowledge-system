# AI RAG + 世界观记忆系统（OpenWebUI + Qdrant + 可切换LLM）

## 1. 项目目标

构建一个 AI 对话系统，支持：

### 核心能力

- 支持 OpenWebUI 作为前端
- 支持多轮对话（session memory）
- 能“持续记住并演化世界观”（小说 / 游戏构建）
- 每次回答都自动融合历史信息
- 支持长期记忆 + 短期记忆分层

### LLM 可切换

- 本地模型（Ollama：Qwen 3.5 9B）
- 云端模型（DeepSeek API）
- OpenAI API（可选）

切换方式必须是 **无代码改动（或最小改动）**

---

# 2. 当前问题

目前系统存在以下问题：

### ❌ rag-api

- 只实现 `/query`
- 没有 session memory
- 没有对话上下文拼接
- index 初始化为空（无意义）

### ❌ OpenWebUI

- 无法正确使用 rag-api 作为 LLM backend
- 没有 OpenAI compatible API

### ❌ memory system

- Qdrant 仅用于 embedding，但没有“对话记忆结构”
- 没有 session_id / role / history 存储

### ❌ LLM绑定

- 代码直接绑定 Ollama / embedding
- 无抽象层，无法切换 DeepSeek

---

# 3. 目标架构（最终形态）

```
┌──────────────────────┐
│      OpenWebUI       │
└─────────┬────────────┘
          │ OpenAI API Compatible
          ▼
┌────────────────────────────┐
│         rag-api            │
│  (FastAPI + Agent Layer)   │
└─────────┬──────────────────┘
          │
          ├──────────────┐
          ▼              ▼
   Qdrant Memory     LLM Adapter Layer
 (long-term memory)   (可切换模型)
          │              │
          │              ├── Ollama (Qwen 3.5 9B)
          │              ├── DeepSeek API
          │              └── OpenAI API
          ▼
   context builder (prompt assembler)
          ▼
        LLM output
```

---

# 4. 必须新增的核心能力

## 4.1 Memory System（最重要）

每一轮对话必须存储：

```
{
  "session_id": "xxx",
  "role": "user | assistant",
  "content": "...",
  "timestamp": 123456,
  "embedding": "vector"
}
```

---

### Memory retrieval流程

每次请求：

1. 保存当前 user input
2. 在 Qdrant 检索相关历史
3. 提取 top-k memory
4. 构造 prompt：

```
[整体设定]
[历史相关记忆]
[最近N轮对话]
[当前问题]
```

---

## 4.2 Session Memory（短期）

- 最近 10~20 轮完整保留
- 不进 embedding（直接拼 prompt）

---

## 4.3 Long-term Memory（长期）

- 存 Qdrant
- 用 embedding 检索相关内容
- 用于世界观一致性

---

## 4.4 Summary Memory（建议）

- 每 20~50 轮生成 summary
- 存入 Qdrant
- 降低 token 压力

---

# 5. LLM抽象层（必须实现）

## 5.1 统一接口

```
class LLMClient:
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError
```

---

## 5.2 Ollama实现

```
class OllamaClient(LLMClient):
    def chat(self, messages):
        ...
```

---

## 5.3 DeepSeek实现

```
class DeepSeekClient(LLMClient):
    def chat(self, messages):
        ...
```

---

## 5.4 切换方式

```
llm = get_llm(provider="ollama | deepseek | openai")
```

要求：

- 不改业务逻辑
- 只改 config

---

# 6. API设计（必须改）

## 6.1 兼容 OpenAI格式（关键）

新增：

```
POST /v1/chat/completions
```

返回：

```
{
  "choices": [
    {
      "message": {
        "content": "..."
      }
    }
  ]
}
```

---

## 6.2 原始接口保留（可选）

```
POST /query
```

但主要用于 debug，不用于 OpenWebUI

---

# 7. Prompt 构造逻辑（核心）

每次请求必须构造：

```
SYSTEM:
你是一个持续世界构建AI（小说/游戏设定助手）

WORLD STATE:
- 世界观摘要（长期 memory summary）
- 核心设定

MEMORY:
- Qdrant检索结果（相关历史）
- 最近 N 轮对话

USER:
当前问题
```

---

# 8. OpenWebUI 接入要求

OpenWebUI 配置：

```
Base URL:
http://rag-api:8000/v1

API Format:
OpenAI Compatible
```

---

# 9. 技术栈

- FastAPI
- Qdrant
- Ollama (Qwen 3.5 9B)
- DeepSeek API（可选）
- sentence-transformers / bge embedding
- OpenWebUI

---

# 10. 当前必须修复的问题（优先级）

## P0（必须）

- [ ]  删除 VectorStoreIndex([])
- [ ]  改为 Qdrant + retrieval
- [ ]  实现 /v1/chat/completions
- [ ]  加 session memory

---

## P1（重要）

- [ ]  LLM Adapter 层
- [ ]  prompt builder
- [ ]  memory retrieval

---

## P2（优化）

- [ ]  summary memory
- [ ]  world state struct
- [ ]  long-term compression

---

# 11. 最终效果

实现后系统能力：

### ✔ 小说模式

- 世界观不会崩
- 角色持续一致
- 设定自动延续

### ✔ 游戏构建模式

- 可逐步构建规则系统
- 状态可记忆

### ✔ 多模型切换

- Ollama 本地
- DeepSeek API
- OpenAI

---

# 12. 一句话总结项目本质

> 这是一个 “带长期记忆 + 可切换LLM + 世界状态维护”的 AI agent 系统，而不是普通 RAG。