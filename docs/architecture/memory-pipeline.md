# Memory Pipeline

异步记忆管道由 `rag-api/application/memory_pipeline_service.py` 实现。

## 入口与边界

- 同步入口：`rag-api/application/memory_service.py`
- 异步入口：`submit_turn(event)`
- 后台工作线程：`start_pipeline()` 启动 `_worker()`

## 核心流程

1. 同步请求完成后，`memory_service` 组装 `MemoryEvent` 并提交到持久化队列。
2. `_worker()` 从 SQLite 队列出队，调用 `_process_turn()`。
3. `_process_turn()` 执行：规则评估/SLM 验证 → 摘要提取 → 归一化与去重 → 写入 Qdrant。
4. 处理成功标记 `done`，失败按重试策略标记 `failed/dead`。

## 关键依赖

- 队列状态机：`rag-api/infrastructure/queue/persistent_queue.py`
- 规则评估：`rag-api/domain/memory/rule_evaluator.py`
- 文本归一与去重：`rag-api/domain/memory/text_utils.py`
- 向量存储：`rag-api/infrastructure/vector/qdrant_store.py`

## 调试建议

- 记忆“丢失”优先检查队列状态与 worker 日志。
- 避免文档内绑定精确行号，优先标注模块路径与函数名。
