# Dependency Rules

- API 层只能依赖 Application 层。
- Application 层可以依赖 Domain、Infrastructure、Prompts、Models。
- Domain 层禁止依赖 API 与 Infrastructure。
- Infrastructure 层禁止反向依赖 API 与 Application。

## 当前约束补充

- Prompt 构建统一经由 `application/prompt_builder.py` 门面，不在编排服务中直接绑定 `prompts/prompt.py`。
- LLM 客户端选择统一经由 `application/llm_gateway.py` 门面，不在编排服务中直接绑定 `infrastructure/llm/llm_client.py`。
- `api/chat.py` 应保持“薄路由”，核心业务留在 `application`。

## 反例（应避免）

- 在 `api/` 中直接访问 Qdrant 或 Session 存储。
- 在 `domain/` 中引入 FastAPI、Qdrant、SQLite 或 LLM 客户端。
- 在文档中维护大量精确行号，导致频繁漂移。
