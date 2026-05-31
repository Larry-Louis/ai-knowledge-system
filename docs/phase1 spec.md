# Memory Scoring Pipeline v1（低成本最优版）

## 🎯 总体目标

构建一个三层记忆筛选系统：

- 90% 数据：Rule + NLP 直接处理
- 9% 数据：SLM 判断
- 1% 数据：LLM 兜底处理

核心目标：

- 最大化成本效率
- 最小化 LLM 调用
- 保证长期记忆质量

---

# 🧱 总体架构

```text
Input Memory
      │
      ▼
Rule Filter (0 cost)
      │
      ▼
NLP Feature Layer (cheap)
      │
      ▼
SLM Router (Qwen2-1.5B)
      │
  ┌───┴───────────┐
  ▼               ▼
Accept / Drop   Uncertain
                    │
                    ▼
              LLM Judge (rare)
                    │
                    ▼
              Final Decision
````

---

# ⚙️ Phase 1 — Rule Filter（0成本）

## 🎯 目标

过滤明显垃圾信息（无需 NLP / 模型）

## 规则（极简）

```python
def rule_filter(text):
    t = text.strip()

    if len(t) < 5:
        return False

    if t in ["ok", "哈哈", "嗯", "好的", "继续"]:
        return False

    if len(set(t)) == 1:
        return False

    return True
```

---

# ⚙️ Phase 2 — NLP Feature Layer（低成本信号）

## 🎯 目标

不判断语义，只提取“信息密度”

---

## Feature 设计

### 1️⃣ 信息密度

```text
density =
  entity_count +
  number_count +
  noun_ratio +
  code_ratio
```

---

### 2️⃣ 结构复杂度

```text
structure =
  length +
  question_mark +
  code_presence
```

---

### 3️⃣ 新颖度（embedding）

```text
novelty = 1 - similarity_to_recent_memory
```

---

### 4️⃣ 时间衰减

```text
recency = exp(-age / 30 days)
```

---

## NLP 综合评分

```text
feature_score =
0.35 * density +
0.25 * structure +
0.25 * novelty +
0.15 * recency
```

---

# ⚙️ Phase 3 — SLM Router（核心决策层）

## 🎯 目标

SLM 只做一个任务：

> 判断是否进入长期记忆

---

## ❌ SLM不做

* 不抽取
* 不总结
* 不评分复杂权重

---

## ✔ SLM输出格式

```json
{
  "keep": true,
  "confidence": 0.82,
  "type": "fact | preference | task | noise"
}
```

---

## 🧠 Prompt

```text
You are a memory filter.

Decide whether this information should be stored long-term.

Return JSON only:

{
  "keep": true/false,
  "confidence": 0-1,
  "type": "fact | preference | task | noise"
}

Content:
{text}
```

---

## 🎯 SLM触发条件

```text
if feature_score > 0.75 → auto accept
if feature_score < 0.35 → auto drop
else → call SLM
```

---

# ⚙️ Phase 4 — 决策融合

```python
if not rule_filter:
    drop

elif feature_score > 0.75:
    accept

elif feature_score < 0.35:
    drop

else:
    result = SLM(text)

    if result["keep"] and result["confidence"] > 0.7:
        accept
    else:
        drop
```

---

# ⚙️ Phase 5 — LLM兜底（极少）

## 触发条件

```text
- SLM confidence 0.4 ~ 0.7
- conflict with existing memory
- semantic ambiguity
```

---

## LLM用途

* 冲突解决
* 语义纠正
* 少量复杂判断

---

# 📊 成本结构

| 层级          | 占比     | 成本 |
| ----------- | ------ | -- |
| Rule Filter | 100%   | 0  |
| NLP Feature | 100%   | 极低 |
| SLM         | 10~20% | 低  |
| LLM         | 1~3%   | 高  |

---

# 🧠 系统本质

一句话：

> 用 cheap signals 做分流，用 SLM 做边界判断，用 LLM 只处理极少数模糊语义。

---

# 🚀 系统收益

## 💰 成本

* LLM调用减少 90%+
* token浪费减少 50~70%

## ⚡ 性能

* 非LLM路径 < 50ms
* 可异步扩展

## 🧠 质量

* 噪声记忆显著下降
* 长期记忆更稳定
* retrieval 更干净

```