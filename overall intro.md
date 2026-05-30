# AI Knowledge System — 总览

## 系统定位

一个带**分层长期记忆** + **可切换 LLM** + **文档智能分析** 的 AI 对话系统，通过 Open WebUI 作为前端。

---

## 系统架构

```
用户 ──→ Open WebUI (:4500)
              │ POST /v1/chat/completions
              ▼
         rag-api (:18000)
              │
        ┌─────┴──────┐
        ▼             ▼
   Qdrant (:6333)   DeepSeek API (云端)
   (向量数据库)       (对话推理)
        │
   Ollama (Docker 内部)
   (nomic-embed-text 向量化)

同时运行的服务：
  doc-reader (:19000) — 文档上传 & 对话分析
  Ollama — embedding 模型 (nomic-embed-text)
```

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 对话记忆 | 每次对话存入 Qdrant，下次搜索相关内容带入上下文 |
| 分层记忆 | `core`(永久) + `general`/`story`/`docreader`(按需激活) |
| 模型切换 | 模型名带 `:role` 后缀可同时切换记忆层 |
| 思维链展示 | DeepSeek `reasoning_content` 透传，Open WebUI 灰色折叠显示 |
| 文档分析 | 上传 .txt/.pdf，自动分章，对话式查询全文档关联 |
| 文档挂载 | 选择文档「挂载」后，对话自动搜索文档内容增强回答 |
| 完整 prompt 查看 | `GET /v1/last-prompt` 查看最近一次请求的完整 prompt |

---

## 服务端口

| 服务 | 端口 | 用途 |
|------|------|------|
| Open WebUI | 4500 | 对话前端界面 |
| rag-api | 18000 | 对话 API + 记忆系统 |
| doc-reader | 19000 | 文档上传 + 文档对话 |
| Qdrant | 6333 | 向量数据库（管理后台） |

---

## 技术栈

- **后端**: FastAPI / Python
- **向量数据库**: Qdrant
- **对话模型**: DeepSeek v4 Flash / Pro (API)
- **Embedding 模型**: nomic-embed-text (Ollama 容器)
- **前端**: Open WebUI
- **容器化**: Docker Compose
