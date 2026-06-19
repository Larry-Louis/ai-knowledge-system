# Phase 1 Production Spec — Memory Admission System (v2.0)

Date: 2026-06-06

> 本文档描述当前**实际实现**的完整处理链路，基于代码而非设计文档。
注意：此文件使用 UTF-8 编码。

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
  |- [S0-1]  API 入口解析                    api/chat.py:73
  |
  |- [S0-2]  会话 ID 推导                    core/memory.py:58
  |
  |- [S0-3]  用户消息向量化                   services/embedding.py:7
  |
  |- [S0-4]  三重记忆检索                     services/qdrant_store.py
  |
  |- [S0-5]  记忆合并去重                     core/memory.py:39
  |
  |- [S0-6]  摘要检索 + 文档检索               services/qdrant_store.py
  |
  |- [S0-7]  核心写入触发（可选）              core/memory.py:107
  |
  |- [S0-8]  构建 RAG 提示                    core/prompt.py:6
  |
  |- [S0-9]  LLM 调用                         core/llm.py
  |
  |- [S0-10] 同步写入：用户消息 -> Qdrant      core/memory.py:143
  |
  |- [S0-11] 同步写入：AI响应 -> Qdrant        core/memory.py:151
  |
  |- [S0-12] 提交异步管道任务                  memory_pipeline.py:53
  |
  |- [S0-13] 条件性摘要生成                    core/memory.py:164
  |
  +- HTTP 200
```

## 各步骤详解

### [S0-1] API 入口解析 -- `api/chat.py:73`

**函数：** `chat_completions()`

- 接收 `POST /v1/chat/completions` 请求，解析 `ChatCompletionRequest`
- 解析 `model` 字段确定角色层（`story` / `general` / `core`）：
  - `model: "story"` -> 设置活跃角色为 `story`
  - `model: "core"` -> 开启核心写入模式（Core Write Mode）
  - `model: "deepseek-v4-flash:story"` -> 同时设置模型和角色
- 调用 `MemoryManager.process_request()` 进行核心处理
- 构建 `ChatCompletionResponse` 返回（支持流式/非流式）

### [S0-2] 会话 ID 推导 -- `core/memory.py:58`

**函数：** `_derive_session_id()`

- 如果请求未携带 `session_id`，从第一条用户消息内容计算 MD5 哈希
- 格式：`"s-" + md5(content)[:16]`
- 保证同一用户的同一轮对话产生稳定 ID

### [S0-3] 用户消息向量化 -- `services/embedding.py:7`

**函数：** `EmbeddingService.embed()`

- 取出最后一条用户消息，调用 Ollama `/api/embed` 接口
- 模型：`nomic-embed-text`，输出 768 维向量
- 这条 embedding 将用于后续所有向量检索

### [S0-4] 三重记忆检索 -- `services/qdrant_store.py`

系统在 LLM 调用前执行 **三种并行查询**：

| 查询 | 函数 | 行号 | 参数 |
|------|------|------|------|
| 会话记忆 | `search_memories()` | 73 | 仅当前 `session_id`，`type=memory`，top_k=8 |
| 全局记忆 | `search_global_memories()` | 100 | 按 `layer IN [core, active_role]` 过滤，top_k=6，core 层 x1.05 |
| 近期跨会话 | `get_recent_global_memories()` | 127 | **仅新会话触发**，排除当前 `session_id`，每角色层最多 2 条 |

**搜索层（layer）策略：**
- 始终包含 `core` 层（核心记忆始终可检索）
- 加上当前活跃角色层（`story` / `general` 等）
- 如果活跃层也是 `core`，不重复添加

### [S0-5] 记忆合并去重 -- `core/memory.py:39`

**函数：** `_merge_memories()`

- 合并三段检索结果（会话记忆 + 全局记忆 + 跨会话记忆）
- 按内容前 100 字符去重（`seen` set）
- 截取最多 **12 条**记忆送入 prompt

### [S0-6] 摘要检索 + 文档检索 -- `services/qdrant_store.py`

**摘要检索：** `get_summary()` (行 191)
- 滚动查询 `type=summary` 的最新记录
- 返回当前世界观摘要文本或 None

**文档检索：** `search_documents()` (行 166)
- 获取当前活跃文档 ID 列表（通过 `/documents/active` 端点设置）
- 在 `documents` 集合中搜索，仅限活跃 `doc_id`
- top_k=4，分数阈值 0.65

### [S0-7] 核心写入触发（可选）-- `core/memory.py:107`

仅在 **Core Write Mode** 开启时触发：
- 检查用户消息是否包含 `CORE_TRIGGERS`（`"记住："` / `"要记得："` / `"写入核心："`）
- 匹配后提取触发词后的文本，向量化，直接以 `layer=core` 写入 Qdrant
- 这是用户显式控制长期记忆的机制

### [S0-8] 构建 RAG 提示 -- `core/prompt.py:6`

**函数：** `build_prompt()`

将检索到的上下文注入系统消息，结构为：

```
[基础系统提示]
  + [当前世界观摘要]       <- 来自 S0-6
  + [相关历史记忆]         <- 来自 S0-5，最多 12 条
  + [文档参考]            <- 来自 S0-6，score >= 0.65
```

最终保留原始请求中的用户/助手消息顺序不变。

### [S0-9] LLM 调用 -- `core/llm.py`

**函数：** `LLMFactory.get().chat()`

- 根据 `Config.LLM_PROVIDER` 选择客户端：Ollama / DeepSeek / OpenAI
- DeepSeek 客户端额外提取 reasoning_content 到 `last_reasoning` 字段
- 返回 LLM 生成的文本响应

### [S0-10] [S0-11] 同步写入 Qdrant -- `core/memory.py:143,151`

> **关键理解：** 这两步写入是 **即时同步** 的，且 **不做任何质量筛选**。它们是 `type=memory` 的原始对话记录，和 S1 的 `type=memory_unit`（经过 SLM 评估+去重）是两套东西。

| 时序 | 内容 | type | 角色层 |
|------|------|------|--------|
| LLM 之后 | 用户最后一条消息 | `memory` | 当前活跃角色层 |
| LLM 之后 | AI 完整响应 | `memory` | 当前活跃角色层 |

**为什么需要即时写 Qdrant：**
- 下一轮对话的 RAG 检索需要最近对话的原始上下文
- 如果等异步管道（S1）完成再写入，下一轮请求就搜不到刚说完的内容
- 所以 S0 写入 = 临时的近期对话记录，不做筛选，供上下文检索用

**过滤：** `_is_auto_task()` (行 10) 检测 Open WebUI 自动生成的任务消息并跳过
- 特征：`"### Task:"` 前缀、`<chat_history>` 标记、仅含 `tags/title/follow_ups` 的 JSON

### [S0-12] 提交异步管道任务 -- `memory_pipeline.py:53`

**函数：** `submit_turn()`

- 创建 `MemoryEvent`（用户消息 + 助手消息 + session_id + 角色层）
- 调用 `PersistentQueue.enqueue()` 写入 SQLite 表
- **不阻塞 HTTP 响应返回**，后台工作线程消费

### [S0-13] 条件性摘要生成 -- `core/memory.py:164`

**函数：** `_generate_summary()`

- 这是那个**分层全局记忆提示词**对应的实现
- 触发条件：该会话消息总数能被 `(SUMMARY_INTERVAL x 2)` 整除
- 默认 `SUMMARY_INTERVAL=30` -> 每 **60 条消息** 触发一次
- 过程：提取近期消息 -> LLM 合成本局摘要 -> 向量化 -> `save_summary()`
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
  |  (模块导入时启动, memory_pipeline.py:191)
  |
  |- [S1-1]  崩溃恢复: recover_stale(30s)
  |
  |- [S1-2]  每10分钟: cleanup(86400s)
  |
  +- 轮询循环 (每2秒)
       |
       |- [S1-3]  PersistentQueue.dequeue(batch=1)
       |     -> 从 SQLite 取出最早一条 pending 记录
       |     -> 标记为 processing
       |
       |- [S1-4]  _process_turn(turn_data)
       |
       |- [S1-4a] 拼接对话文本 "用户: ...\nAI助手: ..."
       |
       |- [S1-4b] slm_validate(对话文本)
       |     -> 调用动态路由 LLM (LLMFactory)
       |     -> 输出结构化 JSON: keep/importance/confidence/tier/type/tag/summaries
       |     -> 默认拒绝策略：无用户事实 -> keep=false
       |
       |- [S1-4c] DecisionMaker.classify_mu(SLM 结果)
       |     -> 决策矩阵（importance x confidence）
       |     -> 输出 store_priority: golden / review / low / drop
       |
       |- [S1-4d] 回退: extract_mus() -- 当 SLM 无摘要时
       |     -> 基于规则：按中文连词/标点分割
       |
       +- [S1-4e] _store_mu(每个摘要) <- 最多 3 个/轮次
             |- normalize() -> 术语标准化
             |- is_duplicate() -> 余弦相似度 >= 0.90 跳过
             |- detect_polarity() -> 极性冲突 -> 旧覆盖
             +- Qdrant.upsert() -> type=memory_unit, 含完整元数据
       |
       |- mark_done() / mark_failed()
       |
       +- 继续轮询
```

## 各步骤详解

### [S1-0] 后台线程启动 -- `memory_pipeline.py:191`

```python
_worker_thread = threading.Thread(target=_worker, daemon=True, name="memory-pipeline")
_worker_thread.start()
```

- 在模块导入时自动启动（`from core.memory_pipeline import ...` 即触发）
- **daemon=True**：不阻止进程退出
- 独立运行于主 HTTP 请求线程之外

### [S1-1] 崩溃恢复 -- `persistent_queue.py:109`

**函数：** `recover_stale(timeout=30)`

- 启动时自动执行一次
- 查找 `status='processing'` 且 `updated_at < now - 30s` 的记录
- 将其重置为 `pending`，使它们能被重新消费
- 解决服务崩溃时卡住的半处理项

### [S1-2] 定期清理 -- `persistent_queue.py:127`

**函数：** `cleanup(max_age=86400)`

- 每 10 分钟执行一次
- 删除 `status IN ('done', 'dead')` 且超过 24 小时的记录
- 防止 SQLite 无限增长

### [S1-3] 出队 -- `persistent_queue.py:65`

**函数：** `dequeue(batch_size=1)`

- 按 `created_at ASC` 取最早的一条 `pending` 记录
- 原子性地更新为 `processing` 状态（防重复消费）
- 返回 `{id, data (dict), retries}`

### [S1-4] 核心处理 -- `memory_pipeline.py:160`

**函数：** `_process_turn()`

这是整个管道最关键的编排函数。依次执行以下子步骤：

---

### [S1-4a] 拼接轮次文本并基础评估

#### [S1-4-Rule] 综合得分评估 -- `core/rule_evaluator.py`

- **结构探测**: 检测 `INSTRUCTION_KEYWORDS` (修改/创建...), 检测 ` ``` ` 代码块，计算字符串长度。
- **倾向分析**: 检测 `POSITIVE_WORDS` 与 `NEGATIVE_WORDS`，并识别 `DISSOLVE_WORDS` (消息删除)。
- **领域模式匹配**: 检测 `DOMAIN_ACTIONS` 与 `DOMAIN_OBJECTS` 的动宾二元匹配。
- **拦截策略**: 综合 score < 0.1 时，直接拦截跳过，不调用 SLM，降低后台负载。

```python
turn_text = f"用户: {turn_data.get('user','')}\nAI助手: {turn_data.get('assistant','')}"
```

- 将整轮对话（用户 + 助手）拼接为一个字符串
- 交由 SLM 评估是否值得记忆

---

### [S1-4b] SLM 验证 -- `core/text_utils.py:68`

**函数：** `slm_validate()`

这是管道的**语义门控**：

- 使用 DeepSeek 扮演 SLM（Small Language Model）角色
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

**输出解析：** `_safe_parse_json()` (行 306)
- 支持多种容错解析：纯 JSON、markdown fence 包裹、正则提取、关键词兜底

---

### [S1-4c] 决策矩阵 -- `core/decision_maker.py:17`

**函数：** `DecisionMaker.classify_mu()`

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

### [S1-4d] 回退提取 -- `core/text_utils.py:53`

**函数：** `extract_mus()`

当 SLM 未返回 summaries 时的兜底方案：
- 按中文连词/标点分割用户消息
- 模式：`r'(?:并且|而且|还|以及|同时|，|。|；|、)'`
- 取前 5 个候选片段（长度 > 4 字符）

---

### [S1-4e] 存储 Memory Unit -- `memory_pipeline.py:90`

**函数：** `_store_mu()`

每个摘要最终通过四步清洗后写入 Qdrant：

**第一步 标准化：** `normalize()` (行 362)
- 主语统一：`"我"` -> `"用户"`，`"我们"` -> `"用户"`
- 术语标准化：大小写统一（autosar -> AUTOSAR, rag -> RAG, python -> Python 等）
- 15 个预置技术名词映射

**第二步 去重：** `is_duplicate()` (行 410)
- 对内容做 embedding（调用 Ollama）
- 在 Qdrant `memory_unit` 类型中搜索 Top 5
- **余弦相似度 >= 0.90 -> 视为重复，跳过存储**

**第三步 极性冲突检测与解决：** `detect_polarity()` (行 392)
- 基于关键词计数判断极性：
  - 正面词：喜欢、爱、支持、推荐...
  - 负面词：不喜欢、讨厌、拒绝、无法...
- 如果新内容极性非中性，且存在语义相似（score >= 0.80）的旧点但极性相反
- **策略：新数据覆盖旧数据**（删除旧点 + 写入新点）

**第四步 写入 Qdrant：** `PointStruct` 包含完整载荷：

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

### [S1-5] 标记完成/失败 -- `persistent_queue.py:83,92`

- **成功：** `mark_done()` -> 状态改为 `done`
- **失败：** `mark_failed()` -> retries++，超 3 次后状态变 `dead`，否则重置为 `pending` 等待重试

---

# 两个阶段的数据对比

| 维度 | 阶段 0（同步） | 阶段 1（异步） |
|------|---------------|---------------|
| **Qdrant `type`** | `memory` | `memory_unit` |
| **内容** | 原始对话（完整） | 提炼摘要（结构化） |
| **元数据** | layer, role, session_id | mu_type, mu_tag, layer_type, importance, confidence, slm_version, store_priority |
| **延迟要求** | 必须在 HTTP 响应内完成 | 可延迟数秒到数分钟 |
| **失败影响** | 用户可见（记忆丢失） | 用户无感知（自动重试） |
| **去重** | 不做 | 余弦相似度 >= 0.90 |
| **冲突解决** | 不做 | 极性检测 + 覆盖 |
| **标准化** | 不做 | 术语统一 + 主语归一 |
| **质量控制** | 全保存 | SLM 评估 + 决策矩阵 |
| **批量处理** | 每请求 1 次 | 后台批量消费 |

---

# 已知未实现部分

1. **review 状态的 LLM 仲裁** -- `core/decision_maker.py:17`
   - 决策矩阵输出了 `review`（importance >= 0.7 但 confidence < 0.7），但代码中没有对 `review` 做任何特殊处理
   - 它和 `golden` 走完全相同的写入路径，`store_priority` 只记录在 payload 里
   - 预期行为：`review` -> 调 LLM 二次判断 -> 决定 golden / low / drop

---

# 关键文件索引

| 文件 | 职责 |
|------|------|
| `api/chat.py` | HTTP 入口，解析请求，构建响应 |
| `core/memory.py` | MemoryManager：阶段 0 的核心编排 |
| `core/memory_pipeline.py` | 阶段 1 的全部逻辑（worker、SLM、MU处理） |
| `core/prompt.py` | RAG 提示构建 |
| `core/llm.py` | LLM 客户端工厂 |
| `core/config.py` | 全局配置 |
| `core/state.py` | 运行时状态（活跃角色、核心写模式、活跃文档） |
| `services/embedding.py` | 向量化服务（Ollama nomic-embed-text） |
| `services/qdrant_store.py` | Qdrant 数据访问层 |
| `services/session_store.py` | 内存会话存储 |
| `services/persistent_queue.py` | SQLite 持久队列 |
