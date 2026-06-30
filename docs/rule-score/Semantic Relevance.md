# Semantic Relevance 设计文档（Phase1 Memory Admission）

# 设计目标

Semantic Relevance 是 Phase1 综合评分系统中最核心的一部分。

它负责回答整个记忆系统最重要的问题：

> **"这段对话，从整体语义上来说，有多像一条值得进入长期记忆的信息？"**

这里强调的是：

**整体语义（Semantic Meaning）**

而不是：

* 是否包含某几个关键词
* 是否命中了某条规则
* 是否出现了某个实体

因此，Semantic Relevance 应当成为整个 Phase1 的**基础评分（Base Score）**。

其它所有规则，仅用于对 Semantic Score 做轻微修正，而不应该主导最终结果。

---

# 为什么需要 Semantic Relevance

如果仅依赖规则：

例如：

```text
喜欢
计划
开发
学习
```

虽然能够识别很多情况，

但是：

```
我准备学习Rust
```

和

```
以后想把通信模块迁移到Adaptive Platform
```

几乎没有共同关键词。

但是它们表达的是同一种语义：

> 用户正在描述未来仍然有价值的信息。

Semantic Relevance 希望识别的正是这种：

> **语义层面的共同特征。**

因此：

Embedding 是 Semantic Relevance 的核心能力。

---

# 从单侧匹配升级为双侧语义空间

最初的设计中：

Semantic Relevance 只有一组 Anchor：

```
Memory Anchor
```

例如：

```
我在做一个项目

我最近在学习

我喜欢这个

我准备下一步

我负责

……
```

算法实际上是在计算：

```
输入

↓

和 Memory Prototype 有多像？
```

最终：

```
score=max(similarity)
```

这种方法存在一个天然的问题。

例如：

```
今天下雨了。
```

可能仍然会与：

```
我最近在学习
```

具有一定的 Embedding 相似度。

由于系统没有"反例"，因此无法判断：

> 它只是"不像 Memory"，还是"明显属于 Non-Memory"。

因此：

Semantic Relevance 应升级为：

**双侧 Prototype Space。**

---

# 双 Prototype Space

Semantic Relevance 不再只有：

```
Memory Prototype
```

而增加另一组：

```
Non-Memory Prototype
```

整个评分不再回答：

> 像不像值得保存？

而回答：

> **更像 Memory，还是更像 Non-Memory？**

即：

```
                Input
                   │
        ┌──────────┴──────────┐
        │                     │
Memory Prototype      Non-Memory Prototype
        │                     │
Similarity A           Similarity B
        │                     │
        └──────────┬──────────┘
                   │
             Semantic Decision
```

因此：

Semantic Relevance 从：

> Similarity Matching

升级为：

> Prototype Classification

这是整个系统最大的改进之一。

---

# Memory Prototype

Memory Prototype 表示：

> **长期记忆空间（Memory Space）**

它并不是：

"应该保存的句子集合"

而是：

> 一组代表"长期用户信息"的语义原型。

例如：

## Identity

```
我是……

我的工作是……

我负责……

我的职业……

```

---

## Project

```
我正在开发……

最近一直在做……

目前负责……

我们团队开发……

```

---

## Preference

```
我喜欢……

我更倾向……

我讨厌……

我习惯……

```

---

## Skill

```
我会……

我不会……

我正在学习……

我熟悉……

```

---

## Goal

```
我准备……

我计划……

以后准备……

下一步……

```

---

## Experience

```
我遇到了……

我成功解决……

最近完成……

以前做过……

```

---

## Long-term State

```
最近一直……

长期……

持续……

目前一直……

```

Memory Prototype 的目标不是覆盖所有句子。

而是覆盖：

> **所有值得长期记忆的语义类型。**

---

# Non-Memory Prototype

Non-Memory Prototype 表示：

> **非长期记忆空间（Non-Memory Space）**

它不是：

"垃圾句子"

而是：

> 不应该进入长期记忆的信息。

例如：

---

## Chat

```
你好

谢谢

好的

收到

哈哈

嗯

```

---

## Temporary Event

```
今天下雨

刚吃饭

准备睡觉

去买菜

刚回来

```

---

## Assistant Instruction

```
帮我翻译

继续

重新回答

详细一点

优化一下

```

---

## Objective Fact

```
微软发布了新版本

天气不错

今天星期五

世界人口增加

```

---

## Pure Question

```
Docker怎么安装？

为什么报错？

Python是什么？

```

这些内容可能有价值，

但：

它们通常不是：

> 用户长期信息。

因此：

应当属于：

Non-Memory Space。

---

# Semantic Scoring

Semantic Relevance 不应仅使用：

```
max similarity
```

而建议采用：

双空间评分。

例如：

首先：

```
Memory Score
```

计算：

Memory Prototype 的：

```
Top-K Similarity
```

例如：

Top3 平均值。

得到：

```
memory_score
```

然后：

计算：

```
Non-Memory Score
```

同样：

```
Top3 Average
```

得到：

```
non_memory_score
```

最后：

综合：

```
semantic_score

=

memory_score

-

non_memory_score
```

或者：

```
α × memory

-

β × non_memory
```

得到最终语义倾向。

这样：

Semantic Score 不再表示：

> "像不像 Memory"

而表示：

> **更偏向哪一个语义空间。**

---

# Strong Match（强匹配）

平均值虽然稳定，

但是：

会损失一种信息：

> 输入几乎与某一句 Prototype 完全一致。

例如：

```
我最近一直在开发一个项目。
```

如果：

```
Prototype：

我最近一直开发一个项目

Similarity

0.96
```

此时：

平均值已经没有意义。

说明：

输入几乎就是 Prototype 本身。

因此：

建议增加：

Strong Match。

例如：

```
if

max_similarity > threshold

↓

直接采用：

max_similarity
```

这样：

能够保证：

典型表达具有最高置信度。

---

# 为什么使用 Top-K，而不是 Max

仅使用：

```
Max Similarity
```

容易受到：

单个 Prototype 的偶然影响。

例如：

```
某一句 Prototype 写得不好。

或者：

Embedding 偶然接近。
```

因此：

建议：

```
Top3 Average
```

原因：

它表示：

> 输入是否稳定地接近某一个语义空间。

比：

Max 更稳定。

而：

Strong Match

负责处理：

真正的高置信匹配。

因此：

二者结合：

既稳定，

又保留典型表达。

---

# Prototype 的持续演进

Prototype 不应该是固定数据。

而应当成为：

系统不断扩充的：

Semantic Space。

未来可以不断增加：

例如：

新增：

```
Relationship

Habit

Workflow

Tool Usage

AI Preference

Programming Style

Game Preference

Reading Habit

Learning Habit

```

Memory Space 会越来越完整。

同样：

Non-Memory Space

也可以不断增加：

例如：

```
AI Prompt

Temporary Question

Greeting

News

Weather

One-shot Instruction

Short Reply

```

整个 Semantic Relevance 将逐渐从：

"句子相似度匹配"

演进为：

**"长期记忆语义空间分类器（Memory Semantic Space Classifier）"。**

---

# Semantic Relevance 的职责

Semantic Relevance 不负责判断：

* 用户是否喜欢某件事；
* 是否包含实体；
* 是否具有高信息密度；
* 是否包含代码；
* 是否属于重要任务。

这些属于其它评分模块。

Semantic Relevance 只负责一件事情：

> **判断一段文本在整体语义上，更接近"长期记忆空间"，还是"非长期记忆空间"。**

它为整个 Phase1 提供最重要、最稳定的基础评分，其余所有评分模块都应建立在这一基础之上，而不是替代它。
