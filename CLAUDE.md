# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

AI Knowledge System 是一个**分布式、双通道 AI 记忆系统**，为 LLM 对话提供分层长期记忆架构。它通过 Open WebUI 进行用户交互，核心逻辑在 rag-api 中实现。

**核心理念**：将对话处理分为两个通道——
- **通道 A（工作记忆）**：在 HTTP 请求生命周期内同步完成，检索相关记忆 → 构建 RAG 提示 → 调用 LLM → 同步写入原始对话记录，确保下一次对话就能立即检索到
- **通道 B（长期记忆）**：异步后台线程处理，经过规则过滤 → SLM 验证 → 去重 → 冲突解决 → 写入高质量记忆单元

## 启动与运行

```powershell
# 启动所有服务
docker compose up -d

# 拉取向量模型（首次或更新后执行）
docker compose exec ollama ollama pull nomic-embed-text

# 查看日志
docker compose logs -f rag-api
docker compose logs -f doc-reader

# 查看 rag-api 内部处理日志（调试记忆问题首选）
# (日志文件位于 rag-api/logs/ 目录，按日轮转)

# 停止所有服务
docker compose down

# 诊断 Qdrant 中的记忆内容
docker compose exec rag-api python check_qdrant.py
```

## 架构与端口

| 服务 | 端口 | 说明 |
|------|------|------|
| open-webui | 8088 | 用户前端界面 |
| ollama | 11434 | 嵌入模型 (nomic-embed-text) 和 SLM |
| qdrant | 6333 | 向量数据库 |
| rag-api | 18000 | 核心后端 (FastAPI)，处理对话与记忆管线 |
| doc-reader | 19000 | 文档摄入与问答服务 |

**依赖关系**：rag-api → qdrant, ollama → open-webui → ollama

## 目录结构

```
ai-knowledge-system/
├── docker-compose.yml       # 5 个服务编排
├── rag-api/                 # 核心后端服务
│   ├── app.py               # FastAPI 入口：health、文档管理、角色管理、warmup
│   ├── api/chat.py          # OpenAI 兼容的 /v1/chat/completions 端点
│   ├── core/
│   │   ├── config.py        # 全局配置（LLM 提供者、模型、层、阈值）
│   │   ├── state.py         # 可变全局状态（活跃角色、文档 ID、core 写入模式）
│   │   ├── memory.py        # MemoryManager：同步管道编排 (S0-2 ~ S0-13)
│   │   ├── memory_pipeline.py # 异步管道：后台 worker、turn 处理、_store_mu
│   │   ├── llm.py           # LLM 抽象层（OllamaClient / DeepSeekClient / OpenAIClient）
│   │   ├── prompt.py        # RAG 提示构建器
│   │   ├── prompt_factory.py # SLM 验证提示模板 (v3.0)
│   │   ├── decision_maker.py# 重要性-置信度决策矩阵
│   │   ├── rule_evaluator.py# 规则预过滤器（结构分 + 极性分 + 领域匹配）
│   │   ├── rule_config.py   # 规则评估器的可调参数
│   │   ├── text_utils.py    # normalize / detect_polarity / is_duplicate / slm_validate
│   │   └── logger.py        # 日志配置（按日轮转）
│   ├── services/
│   │   ├── embedding.py     # 嵌入服务（调用 Ollama /api/embed）
│   │   ├── qdrant_store.py  # Qdrant CRUD（记忆、全局记忆、摘要、文档检索）
│   │   ├── session_store.py # 内存中近期会话历史 (deque, 最多 40 条)
│   │   └── persistent_queue.py # SQLite 持久化任务队列（状态机：pending→processing→done/dead）
│   ├── models/schema.py     # Pydantic 模型（ChatMessage, ChatCompletionRequest/Response）
│   ├── check_qdrant.py      # Qdrant 诊断脚本
│   ├── requirements.txt     # 依赖：fastapi, uvicorn, qdrant-client, httpx
│   └── Dockerfile           # Python 3.10
├── doc-reader/              # 文档摄入服务
│   ├── app.py               # 文件上传、文档列表、文档聊天
│   ├── services/parser.py   # 文档解析（txt/pdf, 分块, 分章）
│   ├── services/indexer.py  # Qdrant documents 集合 CRUD
│   ├── static/index.html    # 单页前端应用
│   └── Dockerfile           # Python 3.11-slim
├── docs/                    # 详细文档
│   ├── phase1 spec.md       # 权威规范文档（逐行分析管线）
│   ├── 手册.md              # 用户手册（快速开始、配置、调试）
│   ├── 当前进度.md          # 完成进度与待办
│   └── 开发计划.md          # Phase 1~5 路线图
├── worker/                  # 遗留文档摄入 worker（当前未使用，不在 docker-compose 中）
└── AGENTS.md                # Agent 开发者指南
```

## 核心数据流

### 对话请求生命周期

```
Open WebUI → POST /v1/chat/completions → api/chat.py (S0-1: 解析 model/role)
    → MemoryManager.process_request() (S0-2 ~ S0-13)
        → EmbeddingService.embed() (S0-3: 向量化用户消息)
        → QdrantStore 三重检索 (S0-4):
            - search_memories()         → 当前会话
            - search_global_memories()  → 全局跨会话（core 层 1.05x 权重提升）
            - get_recent_global_memories() → 新会话预热（2 条最近记忆）
        → 记忆合并去重 (S0-5)
        → 摘要检索 + 文档检索 (S0-6)
        → 核心触发词检查 (S0-7, 可选)
        → build_prompt() (S0-8: 组装 RAG 提示)
        → LLM 调用 (S0-9)
        → 同步写入原始记录到 Qdrant (S0-10, S0-11: type=memory)
        → submit_turn() 入队异步管道 (S0-12)
        → 条件性摘要生成 (S0-13: 每 60 条消息)
    → 返回流式/非流式响应
```

### 异步长期记忆管道

```
后台线程 _worker() (每 2 秒轮询)
    → recover_stale() (S1-1: 启动时恢复卡住项)
    → cleanup() (S1-2: 每 10 分钟清理过期项)
    → dequeue() (S1-3: 出队 pending 项)
    → _process_turn() (S1-4)
        → calculate_rule_score() (S1-4-Rule: 结构分 + 极性分 + 领域匹配)
            → score < 0.1 → 直接丢弃
        → slm_validate() (S1-4b: 调用本地 SLM 验证)
            → keep=false → 丢弃
        → DecisionMaker.classify_mu() (S1-4c: 重要性×置信度矩阵)
        → _store_mu() 对每个摘要 (S1-4e)
            → normalize() 标准化
            → is_duplicate() 去重（余弦相似度 >= 0.90 跳过）
            → Qdrant upsert (type=memory_unit)
```

## Qdrant 数据模型

### `memories` 集合（rag-api）
- **type=memory**：原始对话记录（同步写入），字段：`session_id, role, layer, content, timestamp`
- **type=memory_unit**：长期记忆单元（异步写入），额外字段：`mu_type, mu_tag, layer_type, slm_version, importance, confidence, store_priority, turn_id, source_user, source_assistant`
- **type=summary**：对话摘要（全局单条），额外字段：`session_id=__global__`

### `documents` 集合（doc-reader）
- **type=chapter**：文档分块，字段：`doc_id, doc_title, chapter, title, content, total_chapters`
- 检索阈值：相似度 >= 0.65

## 关键配置点

所有配置集中于 `rag-api/core/config.py`，通过环境变量覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DEEPSEEK_API_KEY | (空) | **必需**，DeepSeek API 密钥 |
| OLLAMA_BASE_URL | http://ollama:11434 | 嵌入模型地址 |
| QDRANT_URL | http://qdrant:6333 | 向量数据库地址 |
| LLM_PROVIDER | ollama | 当前对话 LLM 提供者 |
| TEST_MODE | true | 开启详细调试日志 |

角色层：`general`（默认对话）、`story`（故事创作）、`docreader`（文档分析）
复杂层（`story`, `docreader`）强制使用 deepseek-v4-flash 模型。

## 常见开发任务

### 添加新记忆层
1. 在 `Config.MEMORY_LAYERS` 中添加新层
2. 如需使用 DeepSeek（而非本地模型），添加到 `Config.COMPLEX_LAYERS`
3. 在 `Config.AVAILABLE_MODELS` 中添加可用模型

### 调整记忆准入行为
- `rule_config.py`：调节关键词、极性词、阈值
- `decision_maker.py`：调节 `IMPORTANCE_KEEP`、`IMPORTANCE_HIGH`、`CONFIDENCE_HIGH` 阈值
- `prompt_factory.py`：修改 SLM 验证提示模板（带版本号）

### 调试记忆丢失
1. 查看 rag-api 日志（`rag-api/logs/` 目录的按日文件）
2. 检查 `TEST_MODE` 是否开启以获取详细日志
3. 运行 `docker compose exec rag-api python check_qdrant.py` 查看 Qdrant 内容
4. 检查 SQLite 队列状态（`rag-api/data/` 目录）
5. 确认 `state.py` 中的 `get_core_write_mode()` 未被意外开启（会阻塞非核心记忆）

## 重要注意事项

1. **无自动化测试**：项目没有测试框架，修改后需通过 docker compose 手动验证
2. **版本跟踪**：记忆模型和提示模板均有版本号（`SYSTEM_VERSION`, `SLM_PROMPT_VERSION`），修改 schema 时需考虑 Qdrant 存量数据兼容性
3. **Prompt 管理**：LLM 指令集中在 `prompt_factory.py`，严禁在服务层硬编码 prompt
4. **记忆管线依赖**：修改 `memory_pipeline.py` 或 `state.py` 可能破坏持久化逻辑
5. **已知未实现项**：review 状态二次裁决未执行、极性冲突检测未调用、无批处理聚合、无本地 SLM 部署、无记忆可视化 UI
6. **遗留代码**：`worker/` 目录及其 llama_index 依赖未在 docker-compose 中引用
7. **流式端点**：`/v1/chat/completions?stream=true` 返回值实际是同步生成的，MemoryManager.process_request() 执行完毕后整个响应一次性流式输出
