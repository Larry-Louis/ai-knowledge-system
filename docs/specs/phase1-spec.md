# Phase 1 Production Spec — Memory Admission System (v2.0)

Date: 2026-06-06

> 本文档描述当前**实际实现**的完整处理链路，基于代码而非设计文档。
> 注意：此文件使用 UTF-8 编码。

## 维护说明（2026-06-29）

- 由于近期重构（`prompt_builder` / `llm_gateway` 门面引入），文中部分“精确行号”可能与当前代码不一致。
- 本文以“模块路径 + 函数名 + 阶段职责”为准；精确行号仅作历史参考。
- 关键入口已更新为：
  - Prompt 构建入口：`rag-api/application/prompt_builder.py`（内部调用 `prompts/prompt.py`）
  - LLM 路由入口：`rag-api/application/llm_gateway.py`（内部调用 `infrastructure/llm/llm_client.py`）

---

# 系统总架构：双阶段记忆管道

整个系统分为 **两个阶段** 处理记忆：

| 阶段 | 名称 | 同步/异步 | 路径 | 写入类型 |
|------|------|-----------|------|----------|
| **阶段 0** | 同步记忆通道 | 同步（请求路径内） | HTTP -> LLM -> Qdrant | `type=memory` |
| **阶段 1** | 异步记忆管道 | 异步（后台线程） | SQLite Queue -> SLM -> Qdrant | `type=memory_unit` |

---

# 阶段 0 边界说明

阶段 0 覆盖 **整个同步请求生命周期**，不只到 prompt 构建：

```
收到用户消息 -> 检索记忆 -> 构建 prompt  ->  LLM 调用  -> 写 Qdrant + 提交异步任务 -> HTTP 返回
   (S0-1~S0-8)          (S0-9)               (S0-10~S0-13)
```

LLM 调用（S0-9）是中间一步，S0-10 ~ S0-13 虽然也在同步路径里，但它们是在 LLM 已经返回、HTTP 响应还没发出去之前做的。

---

# 阶段 0 — 同步链路（请求路径）

## 数据流总览

```
POST /v1/chat/completions
  |
  |- [S0-1]  API 入口解析                    rag-api/api/chat.py:74
  |
  |- [S0-2]  会话 ID 推导                    rag-api/application/memory_service.py:91 → 58
  |
  |- [S0-3]  用户消息向量化                   rag-api/application/memory_service.py:101 → infrastructure/embedding/embedding.py:7
  |
  |- [S0-4]  三重记忆检索
  |    |- search_memories                     rag-api/application/memory_service.py:112 → infrastructure/vector/qdrant_store.py:83
  |    |- search_global_memories              rag-api/application/memory_service.py:115 → infrastructure/vector/qdrant_store.py:118
  |    |- get_recent_global_memories          rag-api/application/memory_service.py:121 → infrastructure/vector/qdrant_store.py:153
  |
  |- [S0-5]  记忆合并去重                     rag-api/application/memory_service.py:125 → 39
  |
  |- [S0-6]  摘要检索 + 文档检索
  |    |- get_summary                         rag-api/application/memory_service.py:126 → infrastructure/vector/qdrant_store.py:233
  |    |- search_documents                    rag-api/application/memory_service.py:148 → infrastructure/vector/qdrant_store.py:200
  |
  |- [S0-7]  核心写入触发（可选）              rag-api/application/memory_service.py:131-143（内联逻辑）
  |
  |- [S0-8]  构建 RAG 提示                    rag-api/application/memory_service.py:150 → prompts/prompt.py:6
  |
  |- [S0-9]  LLM 调用                         rag-api/application/memory_service.py:179 → infrastructure/llm/llm_client.py:15/35/58
  |
  |- [S0-10] 同步写入：用户消息 -> Qdrant      rag-api/application/memory_service.py:172 → infrastructure/vector/qdrant_store.py:45
  |
  |- [S0-11] 同步写入：AI响应 -> Qdrant        rag-api/application/memory_service.py:185 → infrastructure/vector/qdrant_store.py:45
  |
  |- [S0-12] 提交异步管道任务                  rag-api/application/memory_service.py:194 → application/memory_pipeline_service.py:54
  |
  |- [S0-13] 条件性摘要生成                    rag-api/application/memory_service.py:202 → 208
  |
  +- HTTP 200
```

## 各步骤详解

### [S0-1] API 入口解析

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/api/chat.py:74` — `chat_completions()` 函数定义 |
| **调用位置** | FastAPI 路由框架自动调用（`@router.post("/v1/chat/completions")` 装饰器注册） |

**函数：** `chat_completions()`

- 接收 `POST /v1/chat/completions` 请求，解析 `ChatCompletionRequest`
- 解析 `model` 字段确定角色层（`story` / `general` / `core`）：
  - `model: "story"` -> 设置活跃角色为 `story`
  - `model: "core"` -> 开启核心写入模式（Core Write Mode）
  - `model: "deepseek-v4-flash:story"` -> 同时设置模型和角色
- 调用 `MemoryManager.process_request()` 进行核心处理
- 构建 `ChatCompletionResponse` 返回（支持流式/非流式）

---

### [S0-2] 会话 ID 推导

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_service.py:58` — `MemoryManager._derive_session_id()` 方法定义 |
| **调用位置** | `rag-api/application/memory_service.py:91` — 在 `process_request()` 内，`session_id` 为空时调用 |

**函数：** `_derive_session_id()`

- 如果请求未携带 `session_id`，从第一条用户消息内容计算 MD5 哈希
- 格式：`"s-" + md5(content)[:16]`
- 保证同一用户的同一轮对话产生稳定 ID

---

### [S0-3] 用户消息向量化

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/embedding/embedding.py:7` — `EmbeddingService.embed()` 类方法定义 |
| **调用位置** | `rag-api/application/memory_service.py:101` — 在 `process_request()` 内，取出最后一条用户消息后调用 |

**函数：** `EmbeddingService.embed()`

- 取出最后一条用户消息，调用 Ollama `/api/embed` 接口
- 模型：`nomic-embed-text`，输出 768 维向量
- 这条 embedding 将用于后续所有向量检索

---

### [S0-4] 三重记忆检索

系统在 LLM 调用前执行 **三种并行查询**：

| 查询 | 函数 | 声明位置 | 调用位置 | 参数 |
|------|------|---------|---------|------|
| 会话记忆 | `search_memories()` | `infrastructure/vector/qdrant_store.py:83` | `application/memory_service.py:112` | 仅当前 `session_id`，`type=memory`，top_k=8 |
| 全局记忆 | `search_global_memories()` | `infrastructure/vector/qdrant_store.py:118` | `application/memory_service.py:115` | 按 `layer IN [core, active_role]` 过滤，top_k=6，core 层 x1.05 |
| 近期跨会话 | `get_recent_global_memories()` | `infrastructure/vector/qdrant_store.py:153` | `application/memory_service.py:121` | **仅新会话触发**，排除当前 `session_id`，每角色层最多 2 条 |

**搜索层（layer）策略：**
- 始终包含 `core` 层（核心记忆始终可检索）
- 加上当前活跃角色层（`story` / `general` 等）
- 如果活跃层也是 `core`，不重复添加

---

### [S0-5] 记忆合并去重

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_service.py:39` — `_merge_memories()` 模块级函数定义 |
| **调用位置** | `rag-api/application/memory_service.py:125` — 在 `process_request()` 内，传入 `related` 和 `global_memories + recent_global` |

**函数：** `_merge_memories()`

- 合并三段检索结果（会话记忆 + 全局记忆 + 跨会话记忆）
- 按内容前 100 字符去重（`seen` set）
- 截取最多 **12 条**记忆送入 prompt

---

### [S0-6] 摘要检索 + 文档检索

**摘要检索：**

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/vector/qdrant_store.py:233` — `QdrantStore.get_summary()` 方法定义 |
| **调用位置** | `rag-api/application/memory_service.py:126` — 在 `process_request()` 内，记忆合并后调用 |

- 滚动查询 `type=summary` 的最新记录
- 返回当前世界观摘要文本或 None

**文档检索：**

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/vector/qdrant_store.py:200` — `QdrantStore.search_documents()` 方法定义 |
| **调用位置** | `rag-api/application/memory_service.py:148` — 在 `process_request()` 内，获取活跃文档 ID 后调用 |

- 获取当前活跃文档 ID 列表（通过 `/documents/active` 端点设置）
- 在 `documents` 集合中搜索，仅限活跃 `doc_id`
- top_k=4，分数阈值 0.65

---

### [S0-7] 核心写入触发（可选）

| 维度       | 位置                                                                      |
| -------- | ----------------------------------------------------------------------- |
| **声明位置** | 内联逻辑，嵌入在 `rag-api/application/memory_service.py:131-143` 的 `process_request()` 内，无独立函数 |
| **调用位置** | 同一位置的条件分支，由 `get_core_write_mode()` 返回 `True` 时触发                       |

仅在 **Core Write Mode** 开启时触发：
- 检查用户消息是否包含 `CORE_TRIGGERS`（`"记住："` / `"要记得："` / `"写入核心："`）
- 匹配后提取触发词后的文本，向量化，直接以 `layer=core` 写入 Qdrant
- 这是用户显式控制长期记忆的机制
- 内部调用链：
  - `EmbeddingService.embed()` → 声明 `infrastructure/embedding/embedding.py:7`，调用在 `memory.py:138`
  - `QdrantStore.upsert_memory()` → 声明 `infrastructure/vector/qdrant_store.py:45`，调用在 `memory.py:139`

---

### [S0-8] 构建 RAG 提示

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/prompts/prompt.py:6` — `build_prompt()` 函数定义 |
| **调用位置** | `rag-api/application/memory_service.py:150` — 在 `process_request()` 内，传入 `messages, summary, memories, doc_chunks` |

**函数：** `build_prompt()`

将检索到的上下文注入系统消息，结构为：

```
[基础系统提示]
  + [当前世界观摘要]       <- 来自 S0-6
  + [相关历史记忆]         <- 来自 S0-5，最多 12 条
  + [文档参考]            <- 来自 S0-6，score >= 0.65
```

最终保留原始请求中的用户/助手消息顺序不变。

---

### [S0-9] LLM 调用

| 维度           | 位置                                                                                                                                  |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| **声明位置**     | `rag-api/infrastructure/llm/llm_client.py:73` — `LLMFactory.get()` 工厂方法定义                                                                                |
| **调用位置**     | `rag-api/application/memory_service.py:176-178` — 在 `process_request()` 内，根据模型选择策略调用工厂方法                                                           |
| **LLM 调用声明** | `rag-api/infrastructure/llm/llm_client.py:15` (Ollama), `rag-api/infrastructure/llm/llm_client.py:35` (DeepSeek), `rag-api/infrastructure/llm/llm_client.py:58` (OpenAI) — 各 `LLMClient.chat()` 实现 |
| **LLM 调用位置** | `rag-api/application/memory_service.py:179` — `llm.chat(final_prompt)`                                                                             |


- 根据 `Config.LLM_PROVIDER` 选择客户端：Ollama / DeepSeek / OpenAI
- DeepSeek 客户端额外提取 reasoning_content 到 `last_reasoning` 字段
- 返回 LLM 生成的文本响应

---

### [S0-10] [S0-11] 同步写入 Qdrant

| 维度             | 位置                                                                         |
| -------------- | -------------------------------------------------------------------------- |
| **声明位置**       | `rag-api/infrastructure/vector/qdrant_store.py:45` — `QdrantStore.upsert_memory()` 方法定义 |
| **S0-10 调用位置** | `rag-api/application/memory_service.py:171` — 写入用户最后一条消息                                  |
| **S0-11 调用位置** | `rag-api/application/memory_service.py:185` — 写入 AI 完整响应                                  |

> **关键理解：** 这两步写入是 **即时同步** 的，且 **不做任何质量筛选**。它们是 `type=memory` 的原始对话记录，和 S1 的 `type=memory_unit`（经过 SLM 评估+去重）是两套东西。

| 时序 | 内容 | type | 角色层 |
|------|------|------|--------|
| LLM 之后 | 用户最后一条消息 | `memory` | 当前活跃角色层 |
| LLM 之后 | AI 完整响应 | `memory` | 当前活跃角色层 |

**为什么需要即时写 Qdrant：**
- 下一轮对话的 RAG 检索需要最近对话的原始上下文
- 如果等异步管道（S1）完成再写入，下一轮请求就搜不到刚说完的内容
- 所以 S0 写入 = 临时的近期对话记录，不做筛选，供上下文检索用

**过滤：** `_is_auto_task()` (`rag-api/application/memory_service.py:10`)

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_service.py:10` — `_is_auto_task()` 函数定义 |
| **S0-10 前调用** | `rag-api/application/memory_service.py:171` — 写入前检查用户消息 |
| **S0-11 前调用** | `rag-api/application/memory_service.py:183` — 写入前检查 AI 响应 |

- 特征：`"### Task:"` 前缀、`<chat_history>` 标记、仅含 `tags/title/follow_ups` 的 JSON

---

### [S0-12] 提交异步管道任务

| 维度 | 位置 |
|------|------|
| **声明位置（事件类）** | `rag-api/application/memory_pipeline_service.py:28` — `MemoryEvent` 类定义 |
| **声明位置（提交函数）** | `rag-api/application/memory_pipeline_service.py:54` — `submit_turn()` 函数定义 |
| **调用位置** | `rag-api/application/memory_service.py:194` — `process_request()` 末尾，创建 `MemoryEvent` 后调用 `submit_turn(event)` |

**函数：** `submit_turn()`

- 创建 `MemoryEvent`（用户消息 + 助手消息 + session_id + 角色层）
- 调用 `PersistentQueue.enqueue()` 写入 SQLite 表
  - `enqueue()` 声明：`rag-api/infrastructure/queue/persistent_queue.py:53`
- **不阻塞 HTTP 响应返回**，后台工作线程消费

---

### [S0-13] 条件性摘要生成

| 维度       | 位置                                                                      |
| -------- | ----------------------------------------------------------------------- |
| **声明位置** | `rag-api/application/memory_service.py:224` — `MemoryManager._generate_summary()` 方法定义 |
| **调用位置** | `rag-api/application/memory_service.py:219` — 在 `process_request()` 末尾，消息计数满足整除条件时调用   |

**函数：** `_generate_summary()`

- 这是那个**分层全局记忆提示词**对应的实现
- 触发条件：该会话消息总数能被 `(SUMMARY_INTERVAL x 2)` 整除
- 默认 `SUMMARY_INTERVAL=30` -> 每 **60 条消息** 触发一次
- 过程：提取近期消息 -> LLM 合成本局摘要 -> 向量化 -> `save_summary()`
- `save_summary()` 声明：`rag-api/infrastructure/vector/qdrant_store.py:252`
- `save_summary()` 先删除旧摘要再写入新摘要（只有一个活跃摘要）
- 下一轮 S0-6 `get_summary()` 读出这个摘要，注入 prompt 的 `[当前世界观摘要]`

---

# Qdrant 中两种不同记录类型

| 谁写入 | type | 是否筛选 | 目的 | 检索范围 |
|--------|------|---------|------|---------|
| S0-10/S0-11（同步） | `memory` | **不筛选**，全量保存 | 近期对话上下文，给下一轮 RAG 用 | session 内 + 跨 session 全局 |
| S1-4e（异步） | `memory_unit` | SLM 评估 + 去重 + 冲突解决 | 高质量结构化知识，长期留存 | 全局 |

两者服务于不同目的，互不干扰。

---

# 阶段 1 — 异步链路（后台管道）

## 数据流总览

```
_worker() 守护线程
  |  (模块导入时启动)
  |
  |- [S1-1]  崩溃恢复: recover_stale(30s)
  |    声明: persistent_queue.py:138 → 调用: memory_pipeline_service.py:69
  |
  |- [S1-2]  每10分钟: cleanup(86400s)
  |    声明: persistent_queue.py:162 → 调用: memory_pipeline_service.py:76
  |
  +- 轮询循环 (每2秒)
       |
       |- [S1-3]  PersistentQueue.dequeue(batch=1)
       |    声明: persistent_queue.py:73 → 调用: memory_pipeline_service.py:81
       |    -> 从 SQLite 取出最早一条 pending 记录
       |    -> 标记为 processing
       |    -> 成功后标记 mark_done (声明: persistent_queue.py:98, 调用: memory_pipeline_service.py:93)
       |    -> 失败后标记 mark_failed (声明: persistent_queue.py:113, 调用: memory_pipeline_service.py:95)
       |
       |- [S1-4]  _process_turn(turn_data)
       |    声明: memory_pipeline_service.py:118 → 调用: memory_pipeline_service.py:92
       |
       |- [S1-4a] 拼接对话文本 "用户: ...\nAI助手: ..."
       |    -> 内联逻辑: memory_pipeline_service.py:131
       |
       |- [S1-4-Rule] 综合得分评估
       |    |- probe_structure_score  声明: rule_evaluator.py:4  → 调用: memory_pipeline_service.py:135
       |    |- detect_information_density  声明: rule_evaluator.py:23 → 调用: memory_pipeline_service.py:136
       |    |- match_domain_pattern   声明: rule_evaluator.py:36 → 调用: memory_pipeline_service.py:136
       |
       |- [S1-4b] slm_validate(对话文本)
       |    声明: text_utils.py:95 → 调用: memory_pipeline_service.py:146
       |    -> 内部调用 LLM (Ollama API)
       |
       |- [S1-4c] DecisionMaker.classify_mu(SLM 结果)
       |    声明: decision_maker.py:17 → 调用: text_utils.py:120 (slm_validate 内部)
       |    -> 决策矩阵（importance x confidence）
       |    -> 输出 store_priority: golden / review / low / drop
       |
       |- [S1-4e] _store_mu(每个摘要) <- 最多 3 个/轮次
       |    声明: memory_pipeline_service.py:99 → 调用: memory_pipeline_service.py:162
       |    |- normalize()      声明: text_utils.py:12  → 调用: memory_pipeline_service.py:102
       |    |- is_duplicate()   声明: text_utils.py:60  → 调用: memory_pipeline_service.py:105
       |    |- Qdrant.upsert()  -> type=memory_unit, 含完整元数据
       |
       |- 继续轮询
```

## 各步骤详解

### [S1-0] 后台线程启动

| 维度 | 位置 |
|------|------|
| **声明位置（工作函数）** | `rag-api/application/memory_pipeline_service.py:66` — `_worker()` 函数定义 |
| **声明位置（启动函数）** | `rag-api/application/memory_pipeline_service.py:169` — `start_pipeline()` 函数定义 |
| **线程创建位置** | `rag-api/application/memory_pipeline_service.py:167` — `threading.Thread(target=_worker, daemon=True, name='memory-pipeline')` |
| **线程启动位置** | `rag-api/application/memory_pipeline_service.py:172` — 在 `start_pipeline()` 内的 `_worker_thread.start()` |

- 在模块导入时自动启动（`from core.memory_pipeline import ...` 即触发）
- **daemon=True**：不阻止进程退出
- 独立运行于主 HTTP 请求线程之外

---

### [S1-1] 崩溃恢复

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/queue/persistent_queue.py:138` — `PersistentQueue.recover_stale()` 方法定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:69` — 在 `_worker()` 启动时，轮询循环前执行一次 |

**函数：** `recover_stale(timeout=30)`

- 启动时自动执行一次
- 查找 `status='processing'` 且 `updated_at < now - 30s` 的记录
- 将其重置为 `pending`，使它们能被重新消费
- 解决服务崩溃时卡住的半处理项

---

### [S1-2] 定期清理

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/queue/persistent_queue.py:162` — `PersistentQueue.cleanup()` 方法定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:76` — 在 `_worker()` 轮询循环内，每 10 分钟执行一次 |

**函数：** `cleanup(max_age=86400)`

- 每 10 分钟执行一次
- 删除 `status IN ('done', 'dead')` 且超过 24 小时的记录
- 防止 SQLite 无限增长

---

### [S1-3] 出队与标记

| 操作                            | 声明位置                      | 调用位置                    | 说明                                    |
| ----------------------------- | ------------------------- | ----------------------- | ------------------------------------- |
| `dequeue(batch_size=1)`       | `persistent_queue.py:73`  | `memory_pipeline_service.py:81` | 按 `created_at ASC` 取最早一条 `pending` 记录 |
| `mark_done(item_id)`          | `persistent_queue.py:98`  | `memory_pipeline_service.py:93` | 处理成功后标记为 `done`                       |
| `mark_failed(item_id, error)` | `persistent_queue.py:113` | `memory_pipeline_service.py:95` | 处理失败后重试，超 3 次变 `dead`                 |

**`enqueue(data, max_retries)`** （由 S0-12 `submit_turn()` 调用）：

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/infrastructure/queue/persistent_queue.py:53` |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:63` — 在 `submit_turn()` 内部 |

---

### [S1-4] 核心处理

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_pipeline_service.py:118` — `_process_turn()` 函数定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:92` — 在 `_worker()` 轮询循环内，出队成功后调用 |

**函数：** `_process_turn()`

这是整个管道最关键的编排函数。依次执行以下子步骤：

---

### [S1-4a] 拼接轮次文本并基础评估

| 维度 | 位置 |
|------|------|
| **声明位置** | 内联逻辑，嵌入在 `_process_turn()` 内，`memory_pipeline_service.py:131` |
| **调用位置** | 同一位置 |

```python
turn_text = f"用户: {turn_data.get('user','')}\nAI助手: {turn_data.get('assistant','')}"
```

- 将整轮对话（用户 + 助手）拼接为一个字符串
- 交由 SLM 评估是否值得记忆

---

### [S1-4-Rule] 综合得分评估

| 函数 | 声明位置 | 调用位置 |
|------|---------|---------|
| `probe_structure_score()` | `rag-api/domain/memory/rule_evaluator.py:4` | `rag-api/application/memory_pipeline_service.py:135` |
| `detect_information_density()` | `rag-api/domain/memory/rule_evaluator.py:23` | `rag-api/application/memory_pipeline_service.py:136` |
| `match_domain_pattern()` | `rag-api/domain/memory/rule_evaluator.py:36` | `rag-api/application/memory_pipeline_service.py:136` |

- **结构探测**: 检测 `INSTRUCTION_KEYWORDS` (修改/创建...)，检测 ` ``` ` 代码块，计算字符串长度。
- **倾向分析**: 检测 `POSITIVE_WORDS` 与 `NEGATIVE_WORDS`，并识别 `DISSOLVE_WORDS` (消息删除)。
- **领域模式匹配**: 检测 `DOMAIN_ACTIONS` 与 `DOMAIN_OBJECTS` 的动宾二元匹配。
- **拦截策略**: 综合 score < 0.1 时，直接拦截跳过，不调用 SLM，降低后台负载。

---

### [S1-4b] SLM 验证

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/text_utils.py:95` — `slm_validate()` 函数定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:146` — 在 `_process_turn()` 内，得分评估通过后调用 |

**内部调用链：**
1. `get_memory_validation_prompt(turn_text)` — 声明：`rag-api/prompts/prompt_factory.py:83`
2. 调用 Ollama `/api/chat` API
3. `_safe_parse_json(text)` — 声明：`rag-api/domain/memory/text_utils.py:84`
4. `DecisionMaker.classify_mu(raw)` — 声明：`rag-api/domain/memory/decision_maker.py:17`

这是管道的**语义门控**：
- 使用本地运行的 DeepSeek: deepseek-r1 扮演 SLM（Small Language Model）角色以节省 token
- 调用 `SLM_PROMPT v3.0`（prompt 约 180 行）
- 参数：`temperature=0.1`（低随机性），`max_tokens=300`

**SLM 输出格式：**

```json
{
  "keep": true,
  "importance": 0.85,
  "confidence": 0.75,
  "tier": "LONG",
  "type": "ENTITY",
  "tag": "identity",
  "summaries": ["用户从事AI开发", "用户技术栈是Python"]
}
```

**核心策略：默认拒绝（Default Reject）**
- 除非明确识别出用户身份/偏好/项目/任务/经验
- AI 的通用知识回答不进入长期记忆
- 用户部分权重 1.0，AI 部分权重 0.6~0.8

**输出解析：** `_safe_parse_json()` (`rag-api/domain/memory/text_utils.py:84`)
- 支持多种容错解析：纯 JSON、markdown fence 包裹、正则提取、关键词兜底

---

### [S1-4c] 决策矩阵

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/decision_maker.py:17` — `DecisionMaker.classify_mu()` 类方法定义 |
| **调用位置** | `rag-api/domain/memory/text_utils.py:120` — 在 `slm_validate()` 内，对 SLM 原始输出进行后处理 |

| 条件 | store_priority | 含义 |
|------|---------------|------|
| importance >= 0.7 AND confidence >= 0.7 | `golden` | 黄金记忆，直接入库 |
| importance >= 0.7 AND confidence < 0.7 | `review` | 高价值但低置信，需复核 |
| importance >= 0.4 AND < 0.7 | `low` | 低优先级，存但不保证召回 |
| importance < 0.4 | `drop` | 丢弃 |

同时映射：
- `type` -> `mu_type`（ENTITY / RELATION / EVENT / TASK）
- `tag` -> `mu_tag`（identity / preference / project / fact / task / knowledge / noise）
- `type` -> `layer_type`（ENTITY/RELATION -> semantic, EVENT/TASK -> episodic）

**当前现状：** `review` 和 `golden` 走完全相同的写入路径，`store_priority` 只被记录在 payload 元数据中，没有 LLM 二次仲裁的逻辑。这是未实现的部分。

---

### [S1-4d] 回退提取（已导入但当前未使用）

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/text_utils.py:80` — `extract_mus()` 函数定义 |
| **调用位置** | ⚠️ 当前代码中未调用。该函数被导入（`memory_pipeline_service.py:18`）但 `_process_turn()` 内已改用直接取 `summaries` / `summary` 字段 |

当 SLM 未返回 summaries 时的兜底方案（原设计）：
- 按中文连词/标点分割用户消息
- 模式：`r'(?:并且|而且|还|以及|同时|，|。|；|、)'`
- 取前 5 个候选片段（长度 > 4 字符）

---

### [S1-4e] 存储 Memory Unit

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_pipeline_service.py:99` — `_store_mu()` 函数定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:162` — 在 `_process_turn()` 内，遍历 summaries 逐条调用 |

每个摘要最终通过以下步骤清洗后写入 Qdrant：

#### 第一步 标准化

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/text_utils.py:12` — `normalize()` 函数定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:102` — 在 `_store_mu()` 入口处 |

- 主语统一：`"我"` -> `"用户"`，`"我们"` -> `"用户"`
- 术语标准化：大小写统一（autosar -> AUTOSAR, rag -> RAG, python -> Python 等）
- 15 个预置技术名词映射

#### 第二步 去重

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/text_utils.py:60` — `is_duplicate()` 函数定义 |
| **调用位置** | `rag-api/application/memory_pipeline_service.py:105` — 在 `_store_mu()` 内，标准化后调用 |

- 对内容做 embedding（调用 Ollama）
- 在 Qdrant `memory_unit` 类型中搜索 Top 5
- **余弦相似度 >= 0.90 -> 视为重复，跳过存储**

#### 第三步 极性冲突检测（当前未主动调用）

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/domain/memory/text_utils.py:38` — `detect_polarity()` 函数定义 |
| **调用位置** | ⚠️ 当前 `_store_mu()` 中未调用。该函数被导入（`memory_pipeline_service.py:18`）但实际未执行极性检测逻辑。预期行为：基于关键词计数判断极性，对语义相似（score >= 0.80）的旧点进行新数据覆盖 |

**预期行为（未实现）：**
- 基于关键词计数判断极性
- 如果新内容极性非中性，且存在语义相似（score >= 0.80）的旧点但极性相反
- **策略：新数据覆盖旧数据**

#### 第四步 写入 Qdrant

| 维度 | 位置 |
|------|------|
| 直接调用 | `rag-api/application/memory_pipeline_service.py:112-114` — `qdrant.client.upsert()` |
| `QdrantStore` 封装方法 | 此处未使用 `upsert_memory()`，而是直接调用底层 client。`upsert_memory()` 声明于 `infrastructure/vector/qdrant_store.py:45` |

`PointStruct` 包含完整载荷：

```json
{
  "id": "uuid",
  "vector": [768维 embedding],
  "payload": {
    "content": "用户从事AI开发",
    "type": "memory_unit",
    "mu_type": "ENTITY",
    "mu_tag": "identity",
    "layer_type": "semantic",
    "slm_version": "v3.0",
    "importance": 0.85,
    "confidence": 0.75,
    "store_priority": "golden",
    "layer": "story",
    "session_id": "s-abc123",
    "turn_id": "a1b2c3d4e5f6",
    "source_user": "原用户消息(截断200字)",
    "source_assistant": "原AI响应(截断200字)",
    "timestamp": 1712345678.0
  }
}
```

---

# 声明位置与调用位置速查表

## 阶段 0：同步链路

| 步骤 | 功能 | 声明位置 | 调用位置 |
|------|------|---------|---------|
| S0-1 | API 入口解析 `chat_completions()` | `api/chat.py:74` | FastAPI 路由框架自动调用 |
| S0-2 | 会话 ID 推导 `_derive_session_id()` | `application/memory_service.py:58` | `application/memory_service.py:91` |
| S0-3 | 向量化 `EmbeddingService.embed()` | `infrastructure/embedding/embedding.py:7` | `application/memory_service.py:101` |
| S0-4a | 会话记忆检索 `search_memories()` | `infrastructure/vector/qdrant_store.py:83` | `application/memory_service.py:112` |
| S0-4b | 全局记忆检索 `search_global_memories()` | `infrastructure/vector/qdrant_store.py:118` | `application/memory_service.py:115` |
| S0-4c | 跨会话检索 `get_recent_global_memories()` | `infrastructure/vector/qdrant_store.py:153` | `application/memory_service.py:121` |
| S0-5 | 合并去重 `_merge_memories()` | `application/memory_service.py:39` | `application/memory_service.py:125` |
| S0-6a | 摘要检索 `get_summary()` | `infrastructure/vector/qdrant_store.py:233` | `application/memory_service.py:126` |
| S0-6b | 文档检索 `search_documents()` | `infrastructure/vector/qdrant_store.py:200` | `application/memory_service.py:148` |
| S0-7 | 核心写入（内联） | `application/memory_service.py:131-143` | 同一位置条件分支 |
| S0-8 | 构建 RAG 提示 `build_prompt()` | `prompts/prompt.py:6` | `application/memory_service.py:150` |
| S0-9 | LLM 工厂 `LLMFactory.get()` | `infrastructure/llm/llm_client.py:73` | `application/memory_service.py:176-178` |
| S0-9b | LLM 调用 `llm.chat()` | `infrastructure/llm/llm_client.py:15/35/58` | `application/memory_service.py:179` |
| S0-10 | 同步写用户消息 `upsert_memory()` | `infrastructure/vector/qdrant_store.py:45` | `application/memory_service.py:172` |
| S0-11 | 同步写 AI 响应 `upsert_memory()` | `infrastructure/vector/qdrant_store.py:45` | `application/memory_service.py:185` |
| S0-12 | 提交异步任务 `submit_turn()` | `application/memory_pipeline_service.py:54` | `application/memory_service.py:194` |
| S0-13a | 摘要生成 `_generate_summary()` | `application/memory_service.py:208` | `application/memory_service.py:202` |
| S0-13b | 保存摘要 `save_summary()` | `infrastructure/vector/qdrant_store.py:252` | `application/memory_service.py:233` (`_generate_summary` 内部) |
| — | 自动任务过滤 `_is_auto_task()` | `application/memory_service.py:10` | `application/memory_service.py:171,183` |

## 阶段 1：异步管道

| 步骤 | 功能 | 声明位置 | 调用位置 |
|------|------|---------|---------|
| S1-0 | 后台线程 `_worker()` | `application/memory_pipeline_service.py:66` | 线程创建于 `memory_pipeline_service.py:167`，启动于 `memory_pipeline_service.py:172` |
| S1-1 | 崩溃恢复 `recover_stale()` | `infrastructure/queue/persistent_queue.py:138` | `application/memory_pipeline_service.py:69` |
| S1-2 | 定期清理 `cleanup()` | `infrastructure/queue/persistent_queue.py:162` | `application/memory_pipeline_service.py:76` |
| S1-3a | 入队 `enqueue()` | `infrastructure/queue/persistent_queue.py:53` | `application/memory_pipeline_service.py:63` |
| S1-3b | 出队 `dequeue()` | `infrastructure/queue/persistent_queue.py:73` | `application/memory_pipeline_service.py:81` |
| S1-3c | 标记完成 `mark_done()` | `infrastructure/queue/persistent_queue.py:98` | `application/memory_pipeline_service.py:93` |
| S1-3d | 标记失败 `mark_failed()` | `infrastructure/queue/persistent_queue.py:113` | `application/memory_pipeline_service.py:95` |
| S1-4 | 核心编排 `_process_turn()` | `application/memory_pipeline_service.py:118` | `application/memory_pipeline_service.py:92` |
| S1-4a | 拼接对话文本（内联） | — | `application/memory_pipeline_service.py:131` |
| S1-4-Rule | 结构探测 `probe_structure_score()` | `domain/memory/rule_evaluator.py:4` | `application/memory_pipeline_service.py:135` |
| S1-4-Rule | 极性得分 `detect_information_density()` | `domain/memory/rule_evaluator.py:23` | `application/memory_pipeline_service.py:136` |
| S1-4-Rule | 领域匹配 `match_domain_pattern()` | `domain/memory/rule_evaluator.py:36` | `application/memory_pipeline_service.py:136` |
| S1-4b | SLM 验证 `slm_validate()` | `domain/memory/text_utils.py:95` | `application/memory_pipeline_service.py:146` |
| S1-4b | SLM 提示构建 `get_memory_validation_prompt()` | `prompts/prompt_factory.py:83` | `domain/memory/text_utils.py:107` (slm_validate 内部) |
| S1-4b | JSON 解析 `_safe_parse_json()` | `domain/memory/text_utils.py:84` | `domain/memory/text_utils.py:118` (slm_validate 内部) |
| S1-4c | 决策矩阵 `DecisionMaker.classify_mu()` | `domain/memory/decision_maker.py:17` | `domain/memory/text_utils.py:120` (slm_validate 内部) |
| S1-4d | 回退提取 `extract_mus()` | `domain/memory/text_utils.py:80` | ⚠️ 已导入但当前未使用 |
| S1-4e | 存储 MU `_store_mu()` | `application/memory_pipeline_service.py:99` | `application/memory_pipeline_service.py:162` |
| S1-4e | 标准化 `normalize()` | `domain/memory/text_utils.py:12` | `application/memory_pipeline_service.py:102` |
| S1-4e | 去重 `is_duplicate()` | `domain/memory/text_utils.py:60` | `application/memory_pipeline_service.py:105` |
| S1-4e | 极性检测 `detect_polarity()` | `domain/memory/text_utils.py:38` | ⚠️ 已导入但当前未在 `_store_mu()` 中调用 |

---

# 已知未实现部分

1. **review 状态的 LLM 仲裁** — `rag-api/domain/memory/decision_maker.py:17`
   - 决策矩阵输出了 `review`（importance >= 0.7 但 confidence < 0.7），但代码中没有对 `review` 做任何特殊处理
   - 它和 `golden` 走完全相同的写入路径，`store_priority` 只记录在 payload 里
   - 预期行为：`review` -> 调 LLM 二次判断 -> 决定 golden / low / drop

2. **极性冲突检测未执行** — `rag-api/domain/memory/text_utils.py:38`
   - `detect_polarity()` 已实现但当前 `_store_mu()` 中未调用
   - 写入 Qdrant 前没有进行极性对比和覆盖

3. **回退提取已导入但未使用** — `rag-api/domain/memory/text_utils.py:80`
   - `extract_mus()` 作为 SLM 无摘要时的兜底方案，被导入但 `_process_turn()` 中未调用
   - 当前代码直接取 `result.get('summaries')` 或 `result.get('summary')`

---

# 关键文件索引

| 文件 | 职责 | 主要声明 |
|------|------|---------|
| `rag-api/api/chat.py` | HTTP 入口，解析请求，构建响应 | `chat_completions()` (74) |
| `rag-api/application/memory_service.py` | MemoryManager：阶段 0 的核心编排 | `process_request()` (67), `_derive_session_id()` (58), `_merge_memories()` (39), `_generate_summary()` (208), `_is_auto_task()` (10) |
| `rag-api/application/memory_pipeline_service.py` | 阶段 1 的全部逻辑 | `_worker()` (66), `_process_turn()` (118), `_store_mu()` (99), `submit_turn()` (54), `MemoryEvent` (28) |
| `rag-api/prompts/prompt.py` | RAG 提示构建 | `build_prompt()` (6) |
| `rag-api/prompts/prompt_factory.py` | SLM 验证提示模板 | `get_memory_validation_prompt()` (83), `SLM_PROMPT` (6) |
| `rag-api/infrastructure/llm/llm_client.py` | LLM 客户端工厂 | `LLMFactory.get()` (73), `OllamaClient.chat()` (15), `DeepSeekClient.chat()` (35), `OpenAIClient.chat()` (58) |
| `rag-api/infrastructure/config/config.py` | 全局配置 | — |
| `rag-api/infrastructure/runtime/state.py` | 运行时状态（活跃角色、核心写模式、活跃文档） | — |
| `rag-api/domain/memory/decision_maker.py` | SLM 结果决策矩阵 | `DecisionMaker.classify_mu()` (17) |
| `rag-api/domain/memory/text_utils.py` | 文本处理工具集 | `normalize()` (12), `detect_polarity()` (38), `is_duplicate()` (60), `extract_mus()` (80), `_safe_parse_json()` (84), `slm_validate()` (95) |
| `rag-api/domain/memory/rule_evaluator.py` | 规则评估器（S1-4-Rule） | `probe_structure_score()` (4), `detect_information_density()` (23), `match_domain_pattern()` (36) |
| `rag-api/infrastructure/embedding/embedding.py` | 向量化服务（Ollama nomic-embed-text） | `EmbeddingService.embed()` (7) |
| `rag-api/infrastructure/vector/qdrant_store.py` | Qdrant 数据访问层 | `upsert_memory()` (45), `search_memories()` (83), `search_global_memories()` (118), `get_recent_global_memories()` (153), `search_documents()` (200), `get_summary()` (233), `save_summary()` (252) |
| `rag-api/infrastructure/session/session_store.py` | 内存会话存储 | — |
| `rag-api/infrastructure/queue/persistent_queue.py` | SQLite 持久队列 | `enqueue()` (53), `dequeue()` (73), `mark_done()` (98), `mark_failed()` (113), `recover_stale()` (138), `cleanup()` (162) |
