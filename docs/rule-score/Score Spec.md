# Phase 1 综合得分评估设计思想（Memory Admission Scoring）

## 为什么要重新划分三个评分函数？

传统 NLP 往往按照技术能力划分模块，例如：

- 结构分析（Structure）
- 情感分析（Sentiment）
- 实体识别（NER）

但对于一个**长期记忆系统（Memory System）**而言，这种划分方式并不能直接回答真正关心的问题。

记忆系统关心的并不是：

> 这句话是什么结构？
> 这句话情绪是积极还是消极？

而是：

> 这段对话是否值得成为未来还能再次使用的长期记忆？

因此，Phase1 不应该按照 NLP 技术划分，而应该按照**记忆价值（Memory Value）**进行划分。

三个评分函数分别负责回答三个完全不同的问题。

---
# 第一维：Semantic Relevance（语义相关性）

对应函数：

match_domain_pattern()

它回答的问题是：

> 用户到底在谈什么？

这是整个评分系统最重要的一层。
它关注的是：

- 用户是否在描述自己
- 用户是否在描述长期状态
- 用户是否在描述项目、经验、偏好、计划、技能等长期信息
- 整体语义是否接近"值得长期记忆"的内容

例如：

我最近开始学习Rust
我准备迁移到Adaptive AUTOSAR
我现在负责一个AI Agent项目
我以后准备换工作

虽然这些句子没有相同关键词，但是它们具有非常接近的语义：

> 用户正在描述自己未来仍然有价值的信息。

因此：

Semantic Relevance 应当主要由 Embedding 决定。
规则（Rule）仅作为轻微修正，而不是主要判断依据。
因为 Embedding 回答的是：

> 这句话整体像不像一条长期记忆。

---
# 第二维：Information Density（信息密度）

建议新增函数：

detect_information_density()

它回答的问题是：

> 这句话包含多少可以被未来再次引用的信息？

注意：

这里关注的不是重要性。

而是：

> 信息是否具体。

例如：

我最近一直在研究ARA::COM

比：

我最近一直在研究一些东西

明显更有价值。

原因不是因为用户喜欢 ARA::COM。

而是：

ARA::COM 是一个可以在未来再次引用的实体。

因此：

Entity 在这里表达的是：

> Information Richness（信息丰富程度）

而不是：

> Preference（偏好）

更不是：

> Importance（重要性）

Entity 的真正价值在于：

它为未来建立了可索引（Indexable）的记忆节点。

以后用户再次提到：

ARA::COM

即可直接召回相关记忆。

除了 Entity，本维度还可以统计：

- Framework
- Project
- Programming Language
- AI Model
- Tool
- Repository
- Library
- API
- Version
- 文件名
- URL
- 技术术语

因此，这一维衡量的是：

> 信息密度（Information Density）

而不是实体数量本身。

---
# 第三维：Personal Commitment（个人关联程度）

建议由：

detect_information_density()

升级而来。
它回答的问题是：

> 用户与这件事情之间存在多深的关联？

这里并不仅仅分析：

- Positive
- Negative

真正需要分析的是：
用户是否表达了：

身份（Identity）

例如：

我是
我负责

我的工作是

---

偏好（Preference）

例如：

我喜欢
我讨厌
我更倾向于

---

计划（Plan）

例如：

准备
计划
以后
下一步

---

长期状态（Long-term State）

例如：

一直
长期
最近都
目前一直

---

观点（Opinion）

例如：

我觉得
我认为
我坚持

这些共同表达的是：

> 用户与该主题之间建立了持续关系。

这种关系，比普通事实更具有长期记忆价值。

例如：

Rust是一门语言

只是事实。

而：

我以后准备一直使用Rust

则表达了用户未来的长期倾向。

因此：

第三维真正衡量的是：

> Personal Commitment（用户投入程度）

而不是简单的 Positive / Negative。

---

三个维度之间的关系
三个维度互不重叠。

Semantic Relevance

回答：

> 用户在谈什么？

决定：

> 是否属于长期话题。

---

Information Density

回答：

> 用户说得具体吗？

决定：

> 是否容易建立长期索引。

---

Personal Commitment

回答：

> 用户与该主题关系有多深？

决定：

> 是否值得长期保存。

三者共同组成：

Memory Value

而不是三个不同角度重复判断重要性。

---

为什么这样划分？

一个真正优秀的长期记忆通常同时具备三个特点：

第一：
它讨论的是长期相关的话题。

第二：
它包含具体、可引用的信息。

第三：
它体现了用户自己的长期关系。

例如：

我最近一直在研究Adaptive AUTOSAR，
准备把公司的通信模块迁移到ARA::COM。

Semantic：

✔ 用户项目

Information：

✔ Adaptive AUTOSAR
✔ ARA::COM

Commitment：

✔ 一直
✔ 准备
✔ 我的项目

因此它天然是一条高质量长期记忆。

而：

微软今天发布了新版本。

虽然：

Information Density 很高，

但是：

Semantic 很低，

Commitment 也几乎没有。

因此：

它更像新闻，而不是用户记忆。

---

Phase1 的目标

需要注意：

Phase1 并不是在判断：

> "这句话是不是一定值得存。"

真正的职责是：

> 快速估计这句话具有多大的长期记忆潜力（Memory Potential）。

因此：

Phase1 更像一个高速过滤器（Fast Memory Filter）。

它负责：

- 放行明显有价值的信息；
- 拦截明显没有价值的信息；
- 将不确定的信息交给后续 SLM 做进一步判断。

因此，三个评分函数本质上是在从不同角度共同估计：

> 这段对话未来是否值得再次被记住。

