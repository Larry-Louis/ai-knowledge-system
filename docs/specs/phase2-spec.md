# Phase 2 Production Spec — Insight Layer & Replay Evaluation (v1.0)

> 维护说明：本文件描述 Phase 2 的当前生产实现，不是纯设计稿。若实现继续演进，应优先同步本 spec、`docs/roadmap/phase2-todo.md` 和对应代码。

## System 总架构：在 Phase 1 之上增加 Insight 层

Phase 2 的目标不是替换 Phase 1，而是在既有的“双通道记忆系统”上，再加一层**稳定、可版本化、可导出、可回放评估**的用户画像洞察层。

```
用户输入 → rag-api (:18000)
               │
               ├─ Channel A: 即时回复 / Working Memory
               │   ├─ Qdrant 记忆检索
               │   ├─ 用户画像快照注入
               │   ├─ Prompt 构建
               │   └─ LLM 回复
               │
               └─ Channel B: 异步记忆沉淀
                   ├─ SQLite 持久队列
                   ├─ SLM 评分 / MU 提取
                   ├─ Normalizer / Dedup / Conflict
                   ├─ Qdrant memory_unit 写入
                   └─ Summary 触发后构建 Insight

Phase 2 新增：
  memory_unit / memory → Insight 压缩
  Insight → 用户画像快照
  画像快照 → Prompt 注入
  会话消息 → Replay 导出
  Replay 数据 → 离线评估 / 批量回放
```

## Phase 2 的核心定义

### Insight

Insight 是从原始记忆中压缩出的、面向长期稳定使用的结构化结论。它的特点是：

- 稳定：优先表示长期不易变化的信息。
- 可版本化：同一 category 下可以迭代更新。
- 可追溯：保留 evidence_refs 指向原始记忆。
- 可导出：可输出 JSON / JSONL 供回放和评估。

### 用户画像快照

用户画像快照是将最近 Insight 按 category 聚合后，转换为 prompt 可消费格式的中间层。它不是最终答案，而是用于增强当前对话的一组稳定上下文。

### Replay

Replay 是把真实会话导出为标准化消息序列，供离线评估脚本、批量回放和后续指标分析使用。

---

## Phase 2 数据流

```
用户消息/历史消息
        │
        ▼
MemoryManager.process_request()
        │
        ├─ [P2-1] build_user_profile_snapshot()
        ├─ [P2-2] build_user_profile_snapshot()
        ├─ [P2-3] build_prompt(..., user_profile=...)
        ├─ [P2-4] LLM.chat()
        ├─ [P2-5] upsert_memory() 写入 user / assistant 消息
        ├─ [P2-6] submit_turn() 进入异步管道
        └─ [P2-7] 条件性摘要触发 _generate_summary()
                     │
                     ▼
              insight_builder.build_from_session()
                     │
                     ├─ 读取最近 memory / memory_unit
                     ├─ 按 category 分组
                     ├─ LLM 压缩或 fallback summary
                     ├─ InsightService.resolve_and_create_insight()
                     └─ upsert_insight() 写入 Qdrant insight 集合

导出与评估路径：

session_store.list_session_ids()
        │
        ├─ export_session_replay(session_id)
        │      └─ 单会话 Replay JSON / JSONL
        │
        └─ export_replay_dataset(session_ids)
               └─ 批量 Replay 数据集
                      └─ phase2_insight_eval.py 离线评估
```

---

## 核心阶段拆分

### Stage 0 — Insight 存储骨架

**目标**：让 Insight 可以独立写入、检索、版本更新。

**实现**：

- 新增 Qdrant insight collection。
- Insight 记录包含 `user_id`、`category`、`content`、`confidence`、`status`、`version`、`evidence_refs`。
- `InsightService.create_insight()` 作为统一入口。
- `resolve_and_create_insight()` 处理重复 / 冲突 / 更新。

**结果**：

- 现在系统不只存“原始记忆”，也存“压缩后的洞察”。

---

### Stage 1 — Insight 版本化与冲突处理

**目标**：同一类洞察不会无限重复，且可以表达变化。

**实现**：

- 语义重复阈值：`DUPLICATE_SIMILARITY_THRESHOLD = 0.88`
- 冲突阈值：`CONFLICT_SIMILARITY_THRESHOLD = 0.62`
- 命中高相似记录时，优先更新已有 Insight。
- 命中显式冲突模式时，将旧记录置为 `conflicted`。
- `version` 随更新递增。

**当前状态**：

- 冲突识别已具备基础规则，但仍是轻量实现，不是完整仲裁器。

---

### Stage 2 — Insight Builder

**目标**：把原始记忆压缩成稳定洞察。

**实现**：

- 从 Qdrant 读取指定 session 的最近记忆：`get_recent_session_memories()`。
- 按内容规则分成 `identity / preference / project / stack / behavior / goal / experience / general` 八类。
- 每个 category 单独生成一条候选 Insight。
- 优先调用 LLM 生成压缩结论，失败时使用 fallback summary。
- 候选结果通过 `InsightService.create_insight()` 落盘。

**结果**：

- Insight 不再依赖人工整理，而是从真实会话自动提炼。

---

### Stage 3 — Prompt 注入用户画像

**目标**：让长期稳定信息真正参与当前回复。

**实现**：

- `MemoryManager.process_request()` 在构建 prompt 前调用 `build_user_profile_snapshot()`。
- `build_prompt(..., user_profile=...)` 将画像写入系统 prompt。
- `prompts/prompt.py` 在 `[用户画像]` 段落中输出分类内容与置信度。

**效果**：

- 当前回复能继承用户长期偏好、项目上下文和技术栈信息。

---

### Stage 4 — 洞察历史与导出

**目标**：洞察可追踪、可审查、可外部消费。

**实现**：

- `list_insight_history()` 返回按 category 分组的历史视图。
- `export_insight_history()` 返回扁平化结构，适合 JSON / JSONL。
- API 暴露 `GET /insights/history`、`GET /insights/export`、`GET /insights/export.jsonl`。

**状态类型**：

- `active`：当前可用。
- `conflicted`：存在冲突，需要人工或后续规则处理。
- `deprecated`：已过时，保留历史但默认不参与画像。

---

### Stage 5 — Replay 导出

**目标**：把真实会话变成可回放的评估数据。

**实现**：

- `SessionStore.list_session_ids()` 枚举当前会话。
- `MemoryManager.export_session_replay(session_id)` 导出单会话消息。
- `MemoryManager.export_replay_dataset(session_ids)` 批量导出多个会话。
- API 暴露 `GET /sessions/export`、`GET /sessions/export.jsonl`、`POST /sessions/export-dataset`、`POST /sessions/export-dataset.jsonl`。

**结果**：

- Phase 2 不只是在线记忆增强，也有离线评估入口。

---

### Stage 6 — 离线评估脚本

**目标**：验证 Insight 压缩是否稳定、是否过度压缩、是否保留关键信息。

**实现**：

- `phase2_insight_eval.py` 支持默认 sample 模式。
- 也支持 `--input-file` 的 replay 模式。
- 支持 JSON / JSONL 输入。
- 输出 builder report、compression ratio、category 统计、冲突探测结果。
- 脚本内置 runtime stubs，以适配缺少外部依赖的最小环境。

**当前状态**：

- 离线评估链路已可运行，但正式大规模基线评估仍需持续补充。

---

## 各步骤详解

### [P2-1] 记忆检索与上下文预热

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_service.py:43` — `process_request()` |
| **调用位置** | HTTP 请求进入后立即执行 |

- 这一段主体仍然是 Phase 1 的同步对话主链路：接收消息、检索当前 session 记忆、检索全局记忆、取摘要、取文档片段、拼 prompt、调用 LLM、写入原始 `memory`。
- Phase 2 在这里新增的不是“检索本身”，而是 **在拼 prompt 之前补一层 Insight 画像**：`build_user_profile_snapshot()`。
- 也就是说，`process_request()` 里真正属于 Phase 2 的变化主要有两处：
  - 在构建 prompt 前生成 `user_profile`。
  - 把 `user_profile` 传给 `build_prompt(..., user_profile=...)`，让 Insight 进入系统提示词。
- 所以这里可以理解为：**Phase 1 的请求主链路 + Phase 2 的画像注入层**，而不是重新实现一条新的检索链路。

---

### [P2-2] 用户画像快照构建

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/insight_service.py:149` — `build_user_profile_snapshot()` |
| **调用位置** | `rag-api/application/memory_service.py:110` |

**输出结构：**

```json
{
  "user_id": "s-xxxx",
  "total_insights": 6,
  "categories": {
    "identity": [
      {
        "content": "...",
        "confidence": 0.78,
        "version": 2,
        "evidence_refs": ["m1", "m3"]
      }
    ]
  }
}
```

- 每个 category 最多输出若干条 Insight。
- 只使用 `active` 状态的记录。

---

### [P2-3] Prompt 注入

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/prompts/prompt.py:1` — `build_prompt()` / `_build_system_content()` |
| **调用位置** | `rag-api/application/memory_service.py:147` |

- `[用户画像]` 作为系统提示的一部分被注入。
- 与 `[当前对话摘要]`、`[相关历史记忆]`、`[文档参考]` 并列。
- 画像信息不是硬编码规则，而是 prompt 上下文。

---

### [P2-4] Insight 压缩与写入

| 维度       | 位置                                                                                  |
| -------- | ----------------------------------------------------------------------------------- |
| **声明位置** | `rag-api/application/insight_builder.py:21` — `InsightBuilder.build_from_session()` |
| **调用位置** | `rag-api/application/memory_service.py:226` — `_generate_summary()` 中               |

**触发策略：**

内嵌于 [[phase1-spec#[S0-13] 条件性摘要生成]] 中的 `_generate_summary()` 函数调用，条件为：

- 触发条件：该会话消息总数能被 `(SUMMARY_INTERVAL x 2)` 整除
- 默认 `SUMMARY_INTERVAL=30` -> 每 **60 条消息** 触发一次

**核心步骤：**

1. 读取最近记忆。
2. 按关键词规则分组。
3. 对每类记忆生成候选洞察。
4. 尝试调用 LLM 压缩。
5. 失败时使用 fallback summary。
6. 写入 `insight` 集合。

**当前实现特征：**

- 不是面向所有记忆的无差别摘要，而是按 category 做稳定压缩。

---

### [P2-5] Insight 重复与冲突处理

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/insight_service.py:23` — `InsightService` |
| **调用位置** | `rag-api/application/insight_builder.py:39` |

**重复处理：**

- 向量相似度高于 0.88 时，更新已有 Insight。

**冲突处理：**

- 关键词模式命中时判定为冲突。
- 旧记录标记为 `conflicted`。
- 新版本继续写入。

**说明：**

- 这是轻量版本的冲突管理，足以支撑当前的洞察迭代，但不是最终仲裁器。

---

### [P2-6] Replay 导出

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/application/memory_service.py:236` — `export_session_replay()` |
| **声明位置** | `rag-api/application/memory_service.py:247` — `export_replay_dataset()` |
| **调用位置** | `rag-api/api/chat.py:21` 起的 `/sessions/*` 路由 |

- 单会话导出适合人工检查。
- 多会话导出适合批量评估和基准测试。

---

### [P2-7] 离线评估

| 维度 | 位置 |
|------|------|
| **声明位置** | `rag-api/phase2_insight_eval.py:1` |
| **调用位置** | 手工运行或脚本化 CI |

**脚本能力：**

- sample 模式：快速检查压缩行为。
- replay 模式：读取导出的真实会话。
- 统计输出：
  - sources
  - created
  - compression_ratio
  - category_counts
  - insights
  - profile

---

## Qdrant 中两种不同记录类型

Phase 2 之后，Qdrant 中至少存在两类核心记录：

| 类型 | 集合 | 用途 |
|------|------|------|
| `memory` / `memory_unit` | `QDRANT_MEMORY_COLLECTION` | 原始记忆、阶段性摘要、对话过程素材 |
| `insight` | `QDRANT_INSIGHT_COLLECTION` | 洞察画像、稳定偏好、长期上下文 |

### 差异

- `memory` 更接近原始事实和对话证据。
- `insight` 更接近可复用的长期结论。
- prompt 同时消费两者，但用途不同。

---

## 已知未实现部分

1. **Insight-first 上下文策略还不够强** — `rag-api/application/memory_service.py`
   - 目前已注入用户画像，但还没有完整的优先级、截断和日志审计策略。
   - 未来应明确 insight / memory / document 的上下文配比。

2. **冲突仲裁仍是轻量规则** — `rag-api/application/insight_service.py`
   - 当前基于关键词与阈值判断。
   - 尚未引入时间权重、证据权重、人工回滚或更严格的版本树。

3. **真实大规模评估基线还未定型** — `rag-api/phase2_insight_eval.py`
   - 脚本可跑，但正式指标体系仍需持续扩展。
   - 需要建立更稳定的长期对照集。

4. **批量回放只是入口，不是最终分析平台** — `rag-api/api/chat.py`
   - 现在能导出数据集，但还没有完整的评估看板、趋势分析和自动打分流水线。

---

## 关键文件索引

| 文件 | 职责 | 主要声明 |
|------|------|------|
| `rag-api/application/memory_service.py` | Phase 2 主编排：prompt 注入、summary 触发、回放导出 | `process_request()`, `_generate_summary()`, `export_session_replay()`, `export_replay_dataset()` |
| `rag-api/application/insight_service.py` | Insight 存储、版本化、冲突、历史与导出 | `InsightRecord`, `create_insight()`, `resolve_and_create_insight()`, `build_user_profile_snapshot()`, `list_insight_history()`, `export_insight_history()` |
| `rag-api/application/insight_builder.py` | 从原始记忆压缩生成 Insight | `InsightBuilder.build_from_session()`, `_group_sources()`, `_compose_candidates()`, `_summarize_category()` |
| `rag-api/prompts/prompt.py` | 系统 prompt 组装，注入用户画像 | `build_prompt()`, `_build_system_content()` |
| `rag-api/application/prompt_builder.py` | prompt 构建 facade | `build_prompt()` |
| `rag-api/infrastructure/vector/qdrant_store.py` | Qdrant 存储层，新增 insight 集合支持 | `upsert_insight()`, `search_insights()`, `get_recent_insights()`, `get_recent_session_memories()` |
| `rag-api/infrastructure/session/session_store.py` | 会话枚举与短期消息存储 | `list_session_ids()` |
| `rag-api/api/chat.py` | HTTP 入口与导出接口 | `/sessions/export`, `/sessions/export.jsonl`, `/sessions`, `/sessions/export-dataset`, `/sessions/export-dataset.jsonl`, `/insights/profile`, `/insights/recent`, `/insights/history`, `/insights/export`, `/insights/export.jsonl`, `/insights/rebuild` |
| `rag-api/phase2_insight_eval.py` | 离线评估与 replay 读取 | sample/replay 模式、builder report、multi-session report |

---

## 结论

Phase 2 已经完成了最关键的三件事：

- 从原始记忆压缩出 Insight。
- 把 Insight 作为用户画像注入在线回复。
- 把真实会话导出为 replay 数据供离线评估。

当前系统已经从“记忆能写入”推进到“记忆能沉淀、能复用、能回放验证”。后续工作的重点不再是基础连通性，而是更强的冲突仲裁、更稳定的上下文策略和更正式的评估基线。