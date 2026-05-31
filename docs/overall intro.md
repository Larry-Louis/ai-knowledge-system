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
        ▼                                ▼
Qdrant (:6333)    DeepSeek API (云端)
 (向量数据库)              (对话推理)
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
| Open WebUI | 8080 | 对话前端界面 |
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

---

# Phase 1 — Memory Admission System

## 概述

Phase 1 构建了一个**解耦实时对话与结构化长期记忆的双通道系统**。对话回复实时返回，记忆处理在后台异步完成。

```
对话回复（同步，不阻塞用户）
        │
        ▼
  异步记忆管道（后台 Worker 线程）
        │
   SQLite 持久化队列 → SLM 评分
   → MU 提取 → Normalizer → Dedup
   → Conflict Resolver → Qdrant 写入
```

## 核心架构

### 双通道设计

| 通道 | 用途 | 特点 |
|------|------|------|
| Channel A — Working Memory | 当前对话连续性 | 不经过 SLM，直接拼入 LLM prompt |
| Channel B — Long-term Memory | 结构化长期记忆 | 异步处理，SLM 门控，提炼后存储 |

### Memory Event = Conversation Turn

每一条记忆对应一个完整的对话轮次（Turn）：

```json
{
  "turn_id": "abc123",
  "user": "用户消息",
  "assistant": "AI回复",
  "timestamp": 1234567890,
  "layer": "story"
}
```

### 数据流

```
用户输入 → 搜 Qdrant → 拼 prompt → DeepSeek 回复 → 回复用户（同步）
                                                          			      │
                                                    				Turn 聚合
                                                          			      │
                                                    			SQLite 队列（持久化）
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │       			   Worker 后台线程          		  │
                                          │   				(崩溃恢复 + 重试 3 次)      		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │     		SLM Validator (DeepSeek)   		  │
                                          │   		keep/drop → type → confidence		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │     		Memory Unit Extractor      			  │
                                          │   		     SLM summaries → 规则后备   		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │        			    Normalizer             			  │
                                          │   			     主语统一 + 术语标准化       		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │  			Dedup（余弦 >0.90 跳过）     		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                          ┌───────────────┴───────────────┐
                                          │  			Conflict（余弦 >0.80 + 极性  		  │
                                          │  				相反 → 新覆盖旧）            		  │
                                          └───────────────┬───────────────┘
                                                          			      │
                                                    				Qdrant 写入
                                             				 (memory_unit 类型)
```

---

## Stage 分拆说明

### Stage 0 — 最小可运行骨架 (MVP Pipeline)

**目标**：让系统能写入记忆，不管质量。

**实现**：

- Turn 聚合：user + assistant 成对处理
- 内存队列：Python `queue.Queue`，异步 Worker 线程
- SLM Validator：调用 DeepSeek 判断 keep/drop，最小 prompt
- Qdrant 写入：通过的 Turn 存储为 `memory_unit`

**不做**：持久化、重试、批量、NLP

---

### Stage 1 — 持久化队列 + 重试

**目标**：记忆不丢失，崩溃可恢复。

**实现**：

- SQLite 持久化队列替代内存队列（`services/persistent_queue.py`）
- 状态机：`pending → processing → done / dead`
- 崩溃恢复：启动时自动将 stuck 的 `processing` 项重置为 `pending`
- 重试机制：失败后最多重试 3 次，超限标记 `dead`
- 定期清理：24 小时前的 `done`/`dead` 记录自动删除
- Worker 轮询间隔 2 秒

---

### Stage 2 — SLM Validator 标准化

**目标**：记忆决策稳定可预期。

**实现**：

- SLM 输出结构固定：`{"keep": bool, "type": str, "confidence": float, "summary": str, "summaries": [str]}`
- Prompt 版本化（当前 v2.2）
- 置信度阈值 0.3（低于此值丢弃）
- Type mapping：
  - `preference` / `fact` → `semantic`（语义型记忆）
  - `project` / `task` → `episodic`（事件型记忆）
  - `noise` → `drop`（丢弃）

---

### Stage 3 — Memory Event = Turn

**目标**：SLM 基于完整上下文做判断。

**实现**：

- 管道以 Turn（user+assistant）为基本单位
- SLM prompt 同时包含用户消息和 AI 回复，而非单条消息
- 解决"你说得对"脱离上下文的问题

---

### Stage 4 — Memory Unit Extractor

**目标**：从对话中提取多条结构化记忆单元。

**实现**：

- SLM 支持 `summaries` 数组输出多条 MU
- 三层后备机制：
  1. SLM 的 `summaries` 数组
  2. SLM 的 `summary` 单条
  3. 规则提取器（按 `并且/而且/还/以及/同时/，/。/；/、` 切分）
- 每轮最多产出 3 条 MU
- 每条 MU 独立走后续管道

---

### Stage 5 — Normalizer + Dedup

**目标**：减少重复记忆，统一表达。

**实现**：

- **Normalizer**（规则表 + 正则）：
  - 句首 `我` → `用户`，`我们` → `用户`
  - 术语大小写统一（`python`→`Python`, `rag`→`RAG` 等 15 条）
- **Dedup**：
  - 余弦相似度 > 0.90 → 跳过，不重复存储
  - 对同一内容重复发送不会产生重复记忆

---

### Stage 6 — Conflict Resolver

**目标**：处理矛盾的记忆（"喜欢" vs "不喜欢"）。

**实现**：

- 极性检测：正向关键词（喜欢/爱/支持）vs 负向关键词（不喜欢/讨厌/拒绝）
- 非中性语句 + 余弦相似度 > 0.80 + 极性相反 → 触发覆盖
- 直接用新记忆覆盖旧记忆（省去 LLM 仲裁）

---

## Qdrant 数据结构

### memories 集合 — 对话记忆

```json
{
  "session_id": "s-xxx",
  "role": "user | assistant",
  "layer": "general | story | docreader | core",
  "content": "原始对话内容",
  "type": "memory",
  "timestamp": 1234567890
}
```

### memories 集合 — Memory Unit（结构化记忆）

```json
{
  "content": "用户喜欢Python开发",
  "type": "memory_unit",
  "mu_type": "preference",
  "layer_type": "semantic",
  "slm_version": "v2.2",
  "confidence": 0.85,
  "layer": "story",
  "session_id": "s-xxx",
  "turn_id": "abc123",
  "source_user": "我喜欢Python",
  "source_assistant": "Python适合AI开发",
  "timestamp": 1234567890
}
```

### documents 集合 — 文档章节

```json
{
  "doc_id": "uuid",
  "doc_title": "文件名",
  "chapter": 1,
  "title": "第1段",
  "content": "段落内容",
  "type": "chapter",
  "total_chapters": 346
}
```

## 关键配置

```python
# rag-api/core/config.py
MEMORY_LAYERS = {
    "general": "默认对话",
    "story": "故事创作与世界观设计",
    "docreader": "文档分析与阅读",
}
CORE_LAYER = "core"
CORE_TRIGGERS = ["记住：", "要记得：", "写入核心："]

# Phase 1 管道参数
# SLM: DeepSeek-v4-flash, temperature=0.1
# 置信度阈值: 0.3
# Dedup 阈值: 0.90
# Conflict 阈值: 0.80
# 每条 Turn 最多 3 条 MU
# Worker 轮询间隔: 2s
# 队列清理: 24h
```
