# Phase 1 未实现项清单

日期：2026-05-31

---

## 一、三阶段路由（架构级）

当前状态：100% 走 SLM（DeepSeek-v4-flash）

| 阶段 | 规划占比 | 实现 | 优先级 |
|------|---------|------|--------|
| Rule Score（纯代码） | ~90% | ❌ 未实现 | 🔴 最高 |
| SLM（本地小模型） | ~9% | ❌ 仍用 DeepSeek API | 🟡 中 |
| LLM 仲裁 | ~1% | ❌ 待记待办 | 🟢 低 |

### 1.1 Rule Score

**规划**：纯代码规则，不依赖任何模型或 NLP。

信号来源：
- 关键词命中（项目/架构/bug/设计等）
- 噪声过滤（测试/闲聊标记）
- 长度加权（太短或太长降权）
- code block 检测

输出：0.0~1.0

判定逻辑：

| base score | 行为 |
|-----------|------|
| < 0.35 | ❌ DROP（不调任何模型） |
| 0.35~0.80 | → SLM 判断 |
| > 0.80 | ✅ AUTO STORE（不调 SLM） |

**目标**：SLM 调用量降至 10~30%，LLM 调用 < 3%

---

### 1.2 Feature Score

信号来源：
- 时间衰减（越旧的记忆权重越低）
- embedding 新颖性（与已有记忆差异度）
- 交互深度（该 Turn 在对话中的位置）

---

### 1.3 Final Score 融合

```python
final_score = 0.4 × rule + 0.4 × feature + 0.2 × semantic
```

当前只用 importance 单一维度，未做加权融合。

---

## 二、Batch Aggregation

**规划**：攒够 N 条或等 T 秒后，将多个 Turn 合并为一个 Batch 一次性送入 SLM。

**现状**：逐条处理，每轮只取 1 条。

**预期收益**：
- SLM 调用次数减少
- 多条 Turn 一起判断，上下文更完整
- 降低 API 成本

---

## 三、SLM 部署

**规划**：用本地小模型（如 Qwen2.5-3B）运行在 Ollama 上，替代 DeepSeek API。

**现状**：仍用 DeepSeek-v4-flash（与对话同一模型），每次调用都花钱。

**候选模型**：
- Qwen2.5-3B（推荐，~6GB 显存）
- Qwen2.5-1.5B（轻量，~3GB）
- Qwen3-1.7B（新模型）

---

## 四、NLP 工具集成

**规划**中用到的 NLP 能力全部跳过，当前仅用硬规则替代：

| 能力 | 规划方案 | 当前替代 | 差距 |
|------|---------|---------|------|
| 句法分析 | spaCy/stanza dependency parsing | ❌ 无 | 无法提取 subject-action-object |
| NER 实体识别 | spaCy/stanza NER | ❌ 无 | 无法识别项目名/技术名 |
| 句子智能切分 | NLP 分句 | 按连接词/标点硬切 | 精度低 |
| 同义归一 | 词向量级别 | 硬编码 15 条术语表 | 覆盖极有限 |
| 极性检测 | 语义分析 | 关键词匹配 | 易误判 |

---

## 五、存储优化

| 项目 | 规划 | 现状 |
|------|------|------|
| `tags` 数组 | 支持多个粗粒度标签 | 当前 `mu_tag` 是单字符串 |
| 预留字段 | `entity`、`compressed_from` | 未添加 |
| 查询排序 | importance + similarity + recency 融合 | 仅按 similarity 排序 |
| Cache 机制 | memory_id → semantic_score 缓存 | 未实现 |

---

## 六、优先级建议

| 优先级 | 项目 | 理由 |
|--------|------|------|
| 🔴 P0 | Rule Score | 不实现则 100% 调 API，架构设计失效 |
| 🔴 P0 | SLM 替换为本地模型 | 同上，成本核心 |
| 🟡 P1 | Batch Aggregation | 进一步减少 API 调用 |
| 🟡 P1 | 查询排序优化 | 提升记忆检索质量 |
| 🟢 P2 | NLP 工具集成 | 提升提取精度，非必要 |
| 🟢 P2 | tags 数组、Cache、预留字段 | 优化性质 |
