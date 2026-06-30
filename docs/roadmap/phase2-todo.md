# Phase 2 To-Do（Insight Memory 记忆压缩层）

日期：2026-07-01

---

## 一、阶段目标（对齐开发计划）

Phase 2 目标：从“存储信息”升级为“提炼用户画像”。

本阶段需要实现：
- 将碎片记忆压缩为稳定洞察（Insight）。
- 建立可回溯、可更新、可冲突消解的 Insight 生命周期。
- 在保证回答质量的前提下，进一步降低 Prompt Token。

截至 2026-07-01 的已完成基线：
- Insight 数据模型与 Qdrant 存储接口已落地。
- Insight Builder 最小闭环已落地，可从会话记忆生成洞察。
- 用户画像快照已可注入 Prompt，上下文开始使用 Insight 优先信息。
- 冲突检测与版本化最小闭环已落地：支持重复洞察合并、旧洞察 conflicted 标记、新版本递增。

---

## 二、范围定义（In Scope）

- Insight 数据模型设计与存储。
- Insight Builder 管道（提取、聚合、归一、冲突处理、写入）。
- Insight 检索与上下文注入（Context Builder 接入）。
- Phase 2 评估基线、回归测试、灰度发布。

Out of Scope（本阶段不做）：
- Episode Memory 完整实现（Phase 3）。
- Memory Distillation 生命周期编排（Phase 4）。
- Knowledge Graph 建模与图查询（Phase 5）。

---

## 三、核心交付物

### 3.1 Insight 数据模型（P0）

建议字段：
- insight_id
- user_id
- category（interest/project/stack/behavior/...）
- content（结构化摘要）
- confidence（0~1）
- evidence_refs（来源记忆 ID 列表）
- status（active/conflicted/deprecated）
- version
- created_at / updated_at / last_verified_at

验收：
- 每条 Insight 可追溯来源。
- 支持版本更新与冲突标记。

### 3.2 Insight Builder 最小闭环（P0）

流程：
- 读取候选原始记忆（优先高分记忆）。
- 按主题聚合（兴趣/项目/技术栈/行为模式）。
- 生成候选 Insight。
- 归一化与去重。
- 写入存储并记录 evidence。

验收：
- 跑通端到端：原始记忆 -> Insight 入库。
- 同一主题重复事实可合并，不产生爆炸性冗余。

### 3.3 冲突处理与稳定性（P0）

场景：
- 旧 Insight 与新证据冲突（如技术偏好变化）。

机制：
- 冲突检测（语义相反/状态变化）。
- 冲突仲裁（基于时间权重 + 证据数量 + 置信度）。
- 版本化保留（避免硬覆盖导致信息丢失）。

验收：
- 冲突样本能正确标记并给出新版本。
- 可回滚到上一稳定版本。

当前实现进度：
- 已实现最小闭环：同类洞察去重、低相似冲突标记、版本递增更新。
- 尚未实现：更复杂的时间权重仲裁、证据数量加权与手动回滚 API。

### 3.4 检索接入与 Prompt 优化（P1）

目标：
- 对话构建上下文时优先用 Insight，减少 raw memory 直接注入量。

待办：
- Context Builder 增加“Insight 优先策略”。
- 设定 raw memory fallback 规则。
- 输出注入日志（使用了哪些 insight，替换了哪些 raw memory）。

验收：
- Prompt token 明显下降且回答质量不明显回退。

### 3.5 评估体系与灰度发布（P1）

待办：
- 构建评估集（兴趣/项目/技术栈/行为模式分层样本）。
- 离线指标：压缩率、稳定性、冲突误判率、可追溯率。
- 在线指标：Token、延迟、回答一致性。
- 灰度策略：小流量 -> 分层扩量 -> 全量。

验收：
- 有固定评估报告模板与留档。
- 灰度期间可观测并可回滚。

### 3.6 离线评估脚本（P1）

- 已补充 `rag-api/phase2_insight_eval.py`，用于在无外部服务依赖的情况下做 Phase2 离线评估。
- 脚本覆盖：
  - 画像压缩率统计
  - category 分布统计
  - 冲突/版本化最小探针
- 当前样例跑通结果（5 条原始记忆）：
  - 生成 3 条 Insight，压缩比 0.6
  - 冲突探针可触发版本递增与状态更新
- 已新增回放样例：`rag-api/evals/phase2_replay.sample.jsonl`
- 脚本支持 `--input-file`，可切换为真实回放集模式。

验收：
- 脚本可直接输出 JSON 报告。
- 后续可把样本集从固定示例扩展为真实回放集。

---

## 四、里程碑计划（建议 4 周）

### Week 1：模型与存储
- 完成 Insight schema 与存储接口。
- 完成最小读写 API。

### Week 2：Builder 主链路
- 打通提取/聚合/归一/去重/写入。
- 完成基础单元测试与样例回放。

### Week 3：冲突与上下文接入
- 完成冲突检测与版本化。
- Context Builder 接入 Insight 优先策略。

### Week 4：评估与灰度
- 跑离线评估与回归。
- 小流量灰度并输出周报。
- 达标后准备全量。

---

## 五、Done Criteria（Phase 2 完成定义）

- 100 条碎片记忆可稳定收敛为约 5~15 条高质量 Insight。
- Insight 具备来源可追溯、版本可追踪、冲突可解释。
- 对话上下文已默认启用 Insight 优先策略。
- 相比 Phase 1 基线，Token 进一步下降（需留有前后对照报告）。
- 关键问答质量不低于当前基线（离线+在线共同验证）。

---

## 六、风险与对策

- 风险：过度压缩导致细节丢失。
  - 对策：保留 evidence_refs + fallback raw memory。

- 风险：画像抖动（频繁改写）。
  - 对策：增加稳定窗口与置信度门槛。

- 风险：冲突误判。
  - 对策：保留版本历史 + 仲裁日志 + 人工抽检样本。

---

## 七、优先级清单（执行版）

| 优先级 | 项目 |
|--------|------|
| 🔴 P0 | Insight 数据模型与存储 |
| 🔴 P0 | Insight Builder 最小闭环 |
| 🔴 P0 | 冲突检测与版本化 |
| 🟡 P1 | Context Builder 接入 Insight 优先 |
| 🟡 P1 | 评估体系与灰度发布 |
| 🟢 P2 | Insight 质量自动化监控与调参面板 |
