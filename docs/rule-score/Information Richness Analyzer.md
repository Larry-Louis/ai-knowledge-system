# SPC：Information Richness Analyzer（信息丰富度评估器）

## 1\. 模块目标（Objective）

Information Richness Analyzer 用于评估一段对话中包含的信息丰富程度（Information Richness）。

该模块不负责判断文本是否应该进入长期记忆，而是评估其是否包含足够具体、可引用、可索引的信息，为后续长期记忆建立提供支撑。

最终输出一个 Information Richness Score，用于参与 Phase1 综合评分。

## 2\. 设计理念（Design Philosophy）

长期记忆不仅要求内容具有长期价值，还要求其具有较高的信息密度。

例如：

我喜欢音乐。
虽然表达了用户偏好，但信息较为抽象。

而：

我喜欢古典音乐，尤其喜欢巴赫和肖邦。

则提供了多个未来可引用的信息节点，因此具有更高的信息丰富度。
因此，本模块关注的是：

文本中包含了多少可被未来再次利用的信息。

而不是：

用户是否喜欢这些内容。

## 3\. 模块职责（Responsibilities）

Information Richness Analyzer 负责回答：

"这段文本包含多少未来仍然具有引用价值的信息？"

它不负责：

判断长期话题（由 Semantic Relevance 完成）
判断用户态度（由 Personal Commitment 完成）
判断最终是否进入记忆

## 4\. 评估维度（Evidence）

模块通过收集多种信息证据（Evidence）综合评估信息丰富度。

### 4.1 Named Objects

识别文本中出现的具体命名对象，例如：

人物
地点
组织
产品
品牌
电影
书籍
游戏
软件
技术名词

命名对象越丰富，通常说明文本越具体。

### 4.2 Noun Phrase（名词短语）

统计具有完整语义的名词短语，例如：

古典音乐
深度学习模型
电动汽车

相比于单个普通名词，完整名词短语具有更高的信息价值。

### 4.3 Numerical Information（数字信息）

统计：

数字
时间
日期
年龄
百分比
数量
距离
金额

数字通常能够提高信息精度。

### 4.4 Attributes（属性描述）

统计修饰信息，例如：

红色汽车
日本料理
无线耳机
长焦镜头

属性越丰富，说明描述越具体。

### 4.5 Relations（关系）

识别对象之间的关系，例如：

我的导师
我的朋友
公司项目
家里的猫

关系信息通常具有较高的长期价值。

### 4.6 Structural Richness（结构丰富度）

统计文本结构，例如：

多个完整句子
并列描述
举例
列举
对比
因果关系

结构越丰富，通常包含的信息越多。

## 5\. 输出（Output）

模块输出：
```
InformationRichnessResult(

   score=0.82,

   evidence={
       "named\_objects": 3,
       "noun\_phrases": 5,
       "numbers": 2,
       "relations": 1,
       "attributes": 4,
       "structure": 2
   }
)
```
其中：

score：综合信息丰富度评分
evidence：各类证据统计，用于调试和后续分析

## 6\. 设计原则（Design Principles）

### 轻量化

模块应优先采用：

规则
Token 特征
POS
Chunk
轻量 NLP Pipeline

避免依赖大型语言模型。

### 可扩展

所有 Evidence 均可独立增加或删除，不影响整体架构。

未来可增加：

URL
文件名
邮箱
API
代码片段
数学公式
图片引用
文档引用

无需修改整体评分框架。

### 与领域无关（Domain Independent）

模块不针对任何特定领域设计。

无论文本涉及：

编程
医疗
体育
摄影
音乐
金融
教育

均采用统一的信息丰富度评估方法。

## 7\. 与其它模块关系

Information Richness Analyzer 是 Phase1 综合评分体系中的第二维。

三个模块分别负责不同目标：

## Semantic Relevance

回答：

"用户在谈什么？"

关注：

长期主题。

## Information Richness

回答：

"用户说得有多具体？"

关注：

未来可引用的信息量。

## Personal Commitment

回答：

"用户与该内容关系有多深？"

关注：

身份、偏好、计划、长期状态等个人关联。

三者共同组成对长期记忆价值（Memory Potential）的综合评估。

