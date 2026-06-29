# Architecture Overview

本仓库当前采用分层架构组织服务内部代码，核心目标是降低耦合并稳定长期演进。

## 服务边界

- `rag-api/`: 主对话与记忆编排服务（FastAPI）。
- `doc-reader/`: 文档摄入与文档对话服务（FastAPI）。
- `legacy/worker/`: 历史 worker 代码，仅作兼容与回溯参考。
- `shared/`: 跨服务共享契约与模型。

## `rag-api` 分层

```text
api/
application/
domain/
infrastructure/
prompts/
models/
```

- `api`: 仅做 HTTP 映射与输入输出协议转换。
- `application`: 用例编排与跨模块策略（例如 `memory_service.py`、`memory_pipeline_service.py`、`prompt_builder.py`、`llm_gateway.py`）。
- `domain`: 纯业务规则（评分、文本规范化、规则判定等）。
- `infrastructure`: 外部依赖实现（Qdrant、SQLite 队列、Embedding、LLM 客户端、运行态）。
- `prompts`: Prompt 模板与工厂。
- `models`: API schema。

## 关键运行流

1. 请求从 `api/chat.py` 进入。
2. `application/memory_service.py` 负责同步链路（检索、构造 prompt、LLM 调用、同步写入、提交异步任务）。
3. `application/memory_pipeline_service.py` 负责异步记忆准入（队列、验证、提取、归一化、去重、写入）。

## 维护建议

- 优先引用“模块级路径”，避免在文档中固化行号。
- 新增编排逻辑时优先放在 `application/`，而非直接写入 `api/` 或 `infrastructure/`。
