# Phase 1 Production Spec — Memory Admission System (Updated v1.1)

Date: 2026-05-31

---

# 🎯 Phase 1 总目标

构建一个：

> 低成本 + 高信噪比 + 可异步扩展的 Memory Admission & Structuring System

核心目标：

1. 控制长期记忆成本（LLM/SLM）
2. 提升记忆质量（减少噪声）
3. 将对话结构化为 Memory Units
4. 支撑后续 Insight / Episodic / Graph Memory 扩展

---

# ❌ Phase 1 不做什么

Phase 1 明确不包含：

- 深度推理记忆（Insight Memory）
- 自主反思机制
- 知识图谱推导
- 长链 reasoning memory
- 实时 memory injection optimization

---

# 🧠 核心设计原则

---

## 1. 双通道记忆系统（关键更新）

系统分为两个完全解耦通道：

### 🟢 Channel A — Working Memory（实时上下文）

```text
Chat History Window → Direct LLM Prompt
````

特点：

* 不经过 SLM
* 不做结构化处理
* 保证实时性
* 允许噪声
* 仅用于“当前对话连续性”

用途：

* 指代消解
* 对话连贯
* 即时上下文理解

---

### 🔵 Channel B — Long-term Memory（结构化记忆）

```text
Memory Pipeline → Qdrant
```

特点：

* 异步处理
* SLM / NLP 处理
* 结构化存储
* 可延迟写入

用途：

* 用户偏好
* 项目状态
* 长期事实
* 行为记录

---

## 2. Memory Event = Conversation Turn（关键更新）

系统不再以 Message 为单位处理记忆，而是：

> Conversation Turn = User + Assistant

---

### Turn结构：

```json
{
  "user": "...",
  "assistant": "...",
  "timestamp": "...",
  "turn_id": "..."
}
```

---

### 为什么必须 Turn 聚合：

解决问题：

* “你说得对”无法脱离上下文
* AI回复必须绑定用户意图
* 避免语义断裂
* 保持对话语义完整性

---

## 3. 非对称信息权重（优化版）

信息来源权重：

| Source            | Weight    |
| ----------------- | --------- |
| User Message      | 1.0       |
| Assistant Message | 0.5 ~ 0.7 |

说明：

* 不再使用固定 0.8 / 0.2
* 权重作为 feature bias 而非硬规则
* User 信号优先，但不绝对

---

## 4. Memory Unit（替代 Atomic Fact）

Phase 1 不再使用“Atomic Fact”，改为：

> Memory Unit（MU）：最小有意义记忆单元

---

### MU定义原则：

* 单一主题
* 单一意图
* 可独立检索
* 保留必要上下文

---

### 示例：

原文：

```text
用户不喜欢海鲜，特别是虾
```

MU：

```text
用户不喜欢海鲜（尤其是虾）
```

---

原文：

```text
用户不喜欢海鲜，并且正在学习AUTOSAR
```

MU：

```text
用户不喜欢海鲜

用户正在学习AUTOSAR
```

---

## 5. Memory Queue 增强（关键更新）

### 🎯 新设计：Memory Event Queue

所有记忆不直接进入 SLM，而是：

```text
Message → Memory Event Queue → Batch Aggregation → SLM
```

---

### Queue职责：

* 解耦 Chat & Memory
* 保证异步处理
* 防止 SLM 阻塞
* 支持高吞吐

---

### 队列单位：

```text
Memory Event = Conversation Turn
```

---

## 6. Batch Aggregation（关键更新）

### 🎯 目标

减少 SLM 调用次数，提高上下文完整性

---

### 聚合单位：

```text
N Turns → Batch
```

或：

```text
Time Window (e.g. 10s)
```

---

### 示例：

```text
Turn1
Turn2
Turn3
```

→ 一次送入 SLM

---

### 优势：

* 上下文完整
* 降低 token 消耗
* 提升 SLM 判断准确率

---

## 7. Memory Routing Layer（无keyword）

职责：

* 结构信号判断
* 不做语义理解
* 决定 DROP / SLM / AUTO

---

### 信号来源：

* entropy
* repetition
* novelty
* structural complexity

---

## 8. Signal Feature Layer

输出：

```text
Signal Score
```

组成：

* 信息密度
* 结构复杂度
* 新颖性（embedding）
* 重复率

---

## 9. Routing Decision Layer

```text
if score < 0.35 → DROP
0.35 ~ 0.80 → SLM
> 0.80 → SLM（或未来AUTO STORE）
```

---

## 10. SLM Validator

职责：

* keep / reject
* type classification
* light normalization

---

### 输出：

```json
{
  "keep": true,
  "type": "preference",
  "confidence": 0.91
}
```

---

## 11. Memory Unit Extractor

职责：

* 将 Turn 转换为 Memory Unit
* 进行 minimal abstraction
* 保留必要上下文

---

## 12. Memory Normalizer

职责：

* 统一表达
* 去冗余
* 标准化语义表达

---

## 13. Dedup / Conflict Layer

规则：

* similarity > 0.9 → update
* contradiction → conflict queue

---

## 14. Storage Schema (Qdrant)

```json
{
  "id": "uuid",
  "content": "用户正在开发AI记忆系统",
  "type": "project",
  "confidence": 0.91,
  "embedding": [],
  "timestamp": 1712345678,
  "metadata": {
    "source": "user",
    "turn_id": "...",
    "layer": "semantic"
  }
}
```

---

# 📊 Phase 1 成功指标

---

## 成本

* LLM调用 < 3%
* SLM调用 < 20%

---

## 质量

* 噪声记忆减少 > 60%
* 重复率降低 > 70%

---

## 性能

* Memory pipeline < 100ms（非LLM路径）
* Queue处理稳定无阻塞

---

# 🧠 Phase 1 本质定义

> Phase 1 是一个“解耦实时对话与结构化长期记忆的双通道 Memory Admission System”

---

# 🚀 Phase 1 输出能力

完成后系统具备：

* 双通道记忆架构
* Turn级记忆建模
* 异步 Memory Queue
* Batch SLM processing
* Memory Unit 结构化存储
* 冲突与去重机制

并为后续：

* Phase 2 Insight Memory
* Phase 3 Episodic Memory
* Phase 4 Graph Memory

提供稳定底座。

# Phase 1 架构图

════════════════════════════════════════════════════════════
                 PHASE 1 MEMORY SYSTEM ARCHITECTURE
════════════════════════════════════════════════════════════


                    			┌────────────────────────┐
                    			│                         USER INPUT                   │
                   			└────────────┬───────────┘
                                                        	     	    │
        			┌───────────────┴───────────────────┐
        			│                                                				     		   │	
        			▼                                             				     		   ▼
┌──────────────────────┐                 		   ┌────────────────────────┐
│             		CHANNEL A   	       │                 		   │   		    CHANNEL B             		│
│  		WORKING MEMORY          │                 		   │   		MEMORY PIPELINE   	        │
│  			(REAL-TIME)         	       │                 		   │  				 (ASYNC)               		│
└──────────────────────┘                 		   └───────────┬────────────┘
        			│                                           					       		   │
        			│                                           					       		   ▼
        			│                               		   		   ┌────────────────────────┐
        			│                               		   		   │ 		     Memory Event Queue     	│
        			│                               		   		   │ 			(Turn-based events)     	│
        			│                               		   		   └───────────┬────────────┘
        			│                                          					       		   │
        			│                                          					       		   ▼
        			│                               		   		   ┌────────────────────────┐
        			│                               		   		   │ 			Batch Aggregator       	        │
        			│                               		   		   │ 		 (time window / N turns) 	   	│
        			│                               		   		   └──────────┬─────────────┘
        			│                                          							 │
        			│                                          							 ▼
        			│                               		   		   ┌────────────────────────┐
        			│                               		   		   │ 		    Memory Routing Layer    	│
        			│                               		   		   │ 			(no keyword, signals)         │
        			│                               		   		   └──────────┬─────────────┘
        			│                                          							  │
        			│                                          							  ▼
        			│                               		   		   ┌────────────────────────┐
        			│                               		   		   │ 			Signal Feature Engine    	│
        			│                               		   		   │ 			density / entropy / etc  	│
        			│                               		   		   └────────────────────────┘
        			│                                          							   │
        			│                                          							   ▼
        			│                               		   		   ┌────────────────────────┐
        			│                               		   		   │ 			Routing Decision                 │
        			│                               		   		   │ 			DROP / SLM / AUTO            │
        			│                               		   		   └────────────────────────┘
        			│                                          						            │
        			│                                                              ┌────────────┴─────────────┐
        			│                     						│                                         				   │
        			▼                     					▼                                         				   ▼
┌────────────────────┐   ┌──────────────────────┐         ┌──────────────────────┐
│ 		LLM PROMPT		  │   │ 		SLM VALIDATOR 		       │         │ 			    DROP                		  │
│ 	      (RAW HISTORY)      	  │   │	       (async batch input)   	       │         │ 		           (noise)              		  │
│                    					  │   └──────────┬───────────┘         └──────────────────────┘
└────────────────────┘              		      │
        			│                           				      ▼
        			│               		┌────────────────────────┐
        			│               		│ 		KEEP / REJECT / TYPE  		     │
        			│               		└──────────┬─────────────┘
        			│                          				      ▼
        			│            		┌──────────────────────────────┐
        			│            		│ 			Memory Unit Extractor         	     │
        			│            		│			 (Turn → MU conversion)        	     │
        			│            		└─────────────┬────────────────┘
        			│                       				      ▼
        			│            		┌──────────────────────────────┐
        			│            		│ 			Memory Normalizer             	     │
        			│            		│ 			(standardize expression)        	     │
        			│            		└─────────────┬────────────────┘
        			│                       				      ▼
        			│            		┌──────────────────────────────┐
        			│            		│ 			Dedup / Conflict Resolver     	     │
        			│            		└─────────────┬────────────────┘
        			│                       		     		      ▼
        			│                 			┌──────────────┐
        			│                 			│  	   QDRANT DB   	 │
        			│                 			│ 	(Semantic Mem)	 │
        			│                 			└──────────────┘
        			│
        			▼
────────────────────────────────────────────────────────────
                 LLM RESPONSE OUTPUT
────────────────────────────────────────────────────────────



════════════════════════════════════════════════════════════
                 KEY DESIGN CONTRACTS
════════════════════════════════════════════════════════════


## WORKING MEMORY (Channel A)
--------------------------------
- 不进入SLM
- 不结构化
- 只保证对话连续性
- 即时注入LLM prompt


## MEMORY EVENT
----------------
- 单位 = Conversation Turn
  (User + Assistant)
- 不使用单条 message


## ASYNC MEMORY PIPELINE
-------------------------
- Queue 解耦 chat & memory
- SLM 永不阻塞用户对话
- Batch processing 提升上下文质量


## MEMORY UNIT
---------------
- 不做 atomic fact explosion
- 做 minimal useful memory unit
- 保留语义完整性 + 可检索性


## WEIGHT PRINCIPLE
--------------------
- User > Assistant
- 但不作为硬规则
- 作为 feature bias


## QDRANT MEMORY
-----------------
- 只存结构化 memory units
- embedding 基于 MU
- 不存 raw dialogue

很好，这一段其实是整个系统里**最容易设计错的一段（也是决定 memory 质量的核心）**。我给你按“工程拆解视角”讲清楚：每一层用什么技术、为什么、怎么实现。

---

# 🧠 这一段链路的本质

你这条链：

```text
SLM VALIDATOR
   ↓
KEEP / REJECT / TYPE
   ↓
Memory Unit Extractor
   ↓
Memory Normalizer
   ↓
Dedup / Conflict Resolver
```

本质不是“一个模型流程”，而是：

> **三种系统叠加：规则系统 + 轻NLP + 小模型 + 少量LLM仲裁**

---

# 🧱 总体分工图（非常关键）

```text
PURE CODE        	      NLP            		SLM            	 	LLM
   	│              		│               	  	  │               		 │
   	▼              		▼              	  	  ▼                  	    	 ▼

Routing      		Feature Stats   	Semantic Judge   Conflict Resolve
Extractor    		Entity/NER      	Keep/Type        	Rare correction
Normalizer   		Embedding       	Confidence       	Ambiguity solve
Dedup        		Similarity
```

---

# ⚙️ 1. SLM VALIDATOR（核心语义门控）

## 🎯 职责

> 判断：这条“是否值得进入长期记忆”

---

## ❌ 不做

* 不做事实拆分
* 不做总结
* 不做去重
* 不做embedding计算

---

## ✔ 做什么（SLM ONLY）

```json
{
  "keep": true/false,
  "type": "preference | fact | project | task | noise",
  "confidence": 0-1
}
```

---

## 🧠 输入

```text
Conversation Turn (user + assistant)
+ optional short context window
```

---

## ⚙️ 实现方式

### ✔ 推荐模型

* Qwen2.5-1.5B
* Qwen3-1.7B
* Mistral 7B (quantized)

---

### ✔ Prompt（关键）

```text
你是个记忆过滤器。
决定这些信息是否需要长期存储。
仅返回JSON格式：

{
  "keep": true/false,
  "type": "fact | preference | project | task | noise",
  "confidence": 0-1
}

用户的消息重要度比AI的消息重要度高。

内容：{content}
```

---

## 🟢 技术本质

* SLM = semantic classifier
* 不参与结构化
* 只做 gating

---

# ⚙️ 2. KEEP / REJECT / TYPE（纯逻辑层）

## 🎯 这一层是“无模型逻辑”

SLM 输出之后：

```text
KEEP / REJECT / TYPE
```

---

## ✔ 实现方式（100% code）

```python
if slm.keep == False:
    drop()

elif slm.confidence < 0.4:
    maybe_drop()

else:
    continue_pipeline()
```

---

## TYPE mapping（纯规则）

```python
type_map = {
    "fact": "semantic",
    "preference": "semantic",
    "project": "episodic",
    "task": "episodic",
    "noise": "drop"
}
```

---

## 🧠 这一层的本质

> 把 SLM 输出“工程化落地”

---

# ⚙️ 3. Memory Unit Extractor（最关键但最容易误解）

## 🎯 职责

> 把 Turn 转成 Memory Unit（MU）

---

## ❗ 这里不是 LLM，也不是 SLM

它应该是：

> **Hybrid（规则 + NLP + optional SLM assist）**

---

# 🧱 三种实现方式（推荐组合）

---

## ✔ A. NLP结构拆分（主力）

### 工具：

* spaCy / stanza
* dependency parsing
* NER
* sentence segmentation

---

### 做什么：

#### 1️⃣ 主语识别

```text
用户 / 我 / 我们
```

---

#### 2️⃣ 谓语结构拆分

```text
AUTOSAR / Ollama / Qdrant
```

---

#### 3️⃣ 实体提取

```text
AUTOSAR / Ollama / Qdrant
```

---

### 输出候选 MU：

```json
[
  "用户正在开发AI记忆系统",
  "用户接入DeepSeek",
  "用户增加文档分析模块"
]
```

---

## ✔ B. lightweight heuristic merge

防止过度拆分：

```python
if same_subject and same_topic:
    merge()
```

---

## ✔ C. optional SLM assist（只在复杂句）

例如：

```text
我以前用Ollama，现在换DeepSeek，还加了文档分析
```

SLM辅助：

```text
split into 3 semantic units
```

---

## 🧠 本质

> Extractor = “语义结构切割器”

---

# ⚙️ 4. Memory Normalizer（统一表达层）

## 🎯 职责

把 MU 变成“标准记忆表达”

---

## ❗ 这一层完全不需要 LLM

只需要：

* NLP + rule + embedding dictionary

---

# 🧱 实现细节

---

## ✔ 1. 同义归一（light NLP）

```text
搞 / 做 / 开发 → 从事
```

---

## ✔ 2. 主语标准化

```text
我 → 用户
我们 → 用户团队（可选）
```

---

## ✔ 3. 行业词规范化（可选字典）

```text
autosar → AUTOSAR
rag → RAG
```

---

## ✔ 4. 时间归一化（optional NLP）

```text
最近 → timestamp
昨天 → date
```

---

## 🧠 本质

> Normalizer = “语言标准化器”

---

# ⚙️ 5. Dedup / Conflict Resolver（最复杂的一层）

这一层分三块：

---

# 🟡 5.1 Dedup（纯 embedding）

## ✔ 技术

* embedding cosine similarity
* Qdrant built-in search

---

## ✔ 逻辑

```python
if similarity > 0.90:
    update_timestamp()
    merge_metadata()
```

---

## ✔ 不需要LLM

---

# 🟠 5.2 Conflict Detection（embedding + rule）

## 示例：

```text
用户喜欢Java
用户不喜欢Java
```

---

## 方法：

### 1️⃣ embedding similarity high

### 2️⃣ polarity opposite (NLP sentiment / rule)

---

## NLP工具

* sentiment classifier
* dependency polarity detection

---

## 输出

```json
{
  "conflict": true,
  "candidates": [...]
}
```

---

# 🔴 5.3 Conflict Resolution（ONLY LLM）

## ❗ 只有这里需要LLM

---

## 触发条件：

* strong contradiction
* high importance memory
* ambiguous preference change

---

## LLM做什么：

```text
Which memory is correct or updated?
```

---

## 输出：

```json
{
  "final_memory": "用户现在不使用Java",
  "status": "override old memory"
}
```

---

# 🧠 总体职责分配（最重要）

---

# ✔ 纯代码（Core logic）

* KEEP / REJECT routing
* dedup threshold
* queue handling
* merge rules
* timestamp update

---

# ✔ NLP（结构理解）

* NER
* dependency parsing
* sentiment
* sentence split
* entity extraction

---

# ✔ SLM（语义门控）

* keep decision
* type classification
* coarse normalization

---

# ✔ LLM（极少）

* conflict resolution
* ambiguous memory correction
* rare semantic arbitration

---

# 🚀 一句话总结整个设计

> Phase 1 的核心不是“用模型做记忆”，而是“用代码 + NLP 搭建骨架，用 SLM 做门控，用 LLM 只解决语义冲突”。

---

如果你下一步要继续优化，我建议你看两个关键升级点：

---

## ① Memory Unit 的“合并策略”（防爆炸核心）

## ② Conflict Resolver 的“记忆优先级系统”（决定系统是否稳定）

这两个是 Phase 1 → Phase 2 的分水岭。