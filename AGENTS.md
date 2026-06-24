# AGENTS.md (开发者指南)

欢迎进入 AI Knowledge System 代码库。本指南旨在帮助 Agent 有效地维护和演进本系统。

## 项目概览

这是一个旨在实现长期记忆、文档分析和 LLM 逻辑推理的分布式 AI 系统。它采用**解耦、异步的记忆准入系统**，在不阻塞主对话响应的前提下处理记忆。

## 系统架构

*   **`rag-api/`**: 核心后端 (FastAPI)，处理对话 API 请求并协调记忆流水线。
*   **`doc-reader/`**: 专门用于文档摄入和对话式分析的服务。
*   **存储**: Qdrant (向量数据库) 用于存储记忆/Embedding，SQLite 用于处理持久化任务队列。
*   **前端**: Open WebUI (通过 `docker-compose.yml` 配置)。

## 核心服务与端口

*   **启动方式**: 使用 `docker-compose up -d`。
*   **关键端口**:
    *   `rag-api`: 18000
    *   `doc-reader`: 19000
    *   `Qdrant`: 6333
*   **配置**: 集中于 `rag-api/core/config.py`。

## 记忆流水线 (核心逻辑)

核心逻辑位于 `rag-api/core/` 中。

1.  **通道 A (工作记忆)**: 即时、同步、上下文相关。
2.  **通道 B (长期记忆)**: 异步处理，由 `rag-api/core/memory_pipeline.py` 控制。
    *   流程: `SQLite 任务队列` → `SLM 验证器` (决策) → `提取单元` → `标准化` → `去重` → `Qdrant 写入`。
    *   **注意事项**: 记忆流水线是异步的，使用 SQLite 状态机处理故障和奔溃恢复。调试记忆丢失问题时，请务必检查 `rag-api/core/state.py` 和 `services/persistent_queue.py`。

## 开发约定

*   **命名规范**: 遵循 Pythonic 规范，采用标准的 FastAPI 结构。
*   **逻辑分离**: 业务逻辑、记忆决策和 Prompt 编排已在 `rag-api/core/` 中解耦。
*   **Prompt 管理**: 使用 `rag-api/core/prompt_factory.py` 管理 LLM 指令；切勿在服务层硬编码 Prompt。

## 常见陷阱 (Gotchas)

1.  **记忆流水线依赖**: 修改 `memory_pipeline.py` 或 `state.py` 可能会破坏数据持久化逻辑。如果功能停止保存数据，务必检查 `rag-api/data/` 中的 SQLite 队列状态。
2.  **版本控制**: 记忆模型和 Prompt 均有版本号。修改 `models/schema.py` 中的数据结构时，务必考虑对 Qdrant 存量数据的兼容性。
3.  **文档读取**: 若文档摄入失败，请检查 `doc-reader` 日志，并确保 `doc-reader/models/` 中的 schema 与 `rag-api` 对齐。

如需了解详细的架构流程和阶段性实施细节，请参考 `docs/overall intro.md` 和 `docs/phase1 spec.md`。
