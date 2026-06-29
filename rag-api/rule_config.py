# 基于规则过滤的配置 (规则评分)
# 这些设置允许在不改动核心逻辑的情况下，对启发式过滤进行微调。
ORIGINAL_SCORE = 0.5  # 任何用户输入的初始分值

# 1. 探测结构设置
# INSTRUCTION_KEYWORDS: 标志用户想要执行特定动作/任务的关键词列表。
INSTRUCTION_KEYWORDS = [
    "修改", "创建", "优化", "修复", "总结", "解释", "分析", 
    "帮我", "部署", "查询", "检索"
]
INSTRUCTION_KEYWORDS_SCORE = 0.3  # 如果存在任何指令关键词，则增加的分值。

# CODE_BLOCK_SCORE: 如果存在 ```（表示包含技术内容），则增加的分值。
CODE_BLOCK_SCORE = 0.2

# LENGTH_MIN/MAX: 用于过滤噪音的长度区间；仅应用于用户输入，在此区间内的为有效输入。
LENGTH_MIN = 10
LENGTH_MAX = 200
# LENGTH_SCORE: 如果用户输入长度不在指定范围内，则减少的分值。
LENGTH_SCORE = 0.4

# 2. 极性过滤设置 (情感倾向)
POSITIVE_WORDS = {"好", "支持", "推荐", "可以", "需要", "搞定"}
NEGATIVE_WORDS = {"拒绝", "反对", "不行", "出错", "bug", "失败"}
DISSOLVE_WORDS = {"刚才不算", "开玩笑的", "手抖了"}

# 3. 领域模式匹配器设置
# DOMAIN_ACTIONS: 特定于系统业务领域的动作。
DOMAIN_ACTIONS = {
    "修复", "部署", "创建", "调研", "优化", "检索",
    # 补充：高频开发动作
    "开发", "实现", "设计", "重构", "迁移", "集成", "接入",
    "测试", "调试", "排查", "配置", "搭建", "改造",
    # 补充：口语化表达
    "做", "写", "搞", "跑", "加", "删", "改",
    # 补充：个人状态/决策动作（记忆系统特别需要）
    "考虑", "计划", "打算", "决定", "放弃", "切换", "尝试",
    "学习", "研究", "负责", "参与", "主导",
}
# DOMAIN_OBJECTS: 特定于系统业务领域的实体/对象。
DOMAIN_OBJECTS = {
    "接口", "逻辑", "知识库", "模型", "代码", "API",
    # 补充：技术对象
    "服务", "数据库", "向量库", "pipeline", "embedding",
    "配置", "环境", "依赖", "框架", "架构", "方案",
    "文档", "测试", "脚本", "工具", "系统", "平台",
    # 补充：项目/组织对象（记忆系统需要）
    "项目", "功能", "模块", "需求", "版本", "上线",
    "团队", "方向", "目标", "任务",
}
# 同时匹配到两者将显著提高置信度评分。

# 4. 语义锚点句子（用于语义相关性评分）
# 按文档 Semantic Relevance.md 分为七组 Memory Prototype
# 每组代表一种值得长期记忆的用户信息类型
ANCHOR_GROUPS = {
    "Identity": [
        "我的工作是",
        "我负责",
        "我的职业是",
        "我是一名",
    ],
    "Project": [
        "我在做一个项目",
        "我们团队正在开发",
        "最近一直在做",
        "我正在开发",
        "目前负责一个",
    ],
    "Preference": [
        "我喜欢这个东西",
        "我不喜欢这个",
        "我更喜欢",
        "我习惯",
        "我讨厌",
    ],
    "Skill": [
        "我擅长这方面",
        "我不太会这个",
        "我最近在学习",
        "我会",
        "我熟悉",
    ],
    "Goal": [
        "我打算做这件事",
        "我计划下一步",
        "我准备",
        "以后准备",
        "下一步打算",
    ],
    "Experience": [
        "我遇到了一个问题",
        "我成功解决了",
        "最近完成了一个",
        "以前做过",
    ],
    "LongTermState": [
        "最近一直",
        "长期",
        "持续在",
        "目前一直",
    ],
}

# 展平为列表，保持向后兼容（单空间评分时使用）
ANCHOR_SENTENCES = [s for group in ANCHOR_GROUPS.values() for s in group]

# 5. 非记忆锚点句子（Non-Memory Prototype）
# 按 Semantic Relevance.md 分为五组
NON_MEMORY_ANCHOR_GROUPS = {
    "Chat": [
        "你好",
        "谢谢",
        "好的",
        "收到",
        "哈哈",
        "嗯",
    ],
    "TemporaryEvent": [
        "今天下雨",
        "刚吃饭",
        "准备睡觉",
        "去买菜",
        "刚回来",
    ],
    "AssistantInstruction": [
        "帮我翻译",
        "继续",
        "重新回答",
        "详细一点",
        "优化一下",
    ],
    "ObjectiveFact": [
        "天气不错",
        "今天星期五",
        "微软发布了新版本",
    ],
    "PureQuestion": [
        "Docker怎么安装",
        "为什么报错",
        "Python是什么",
    ],
}

# 展平为列表，保持向后兼容
NON_MEMORY_ANCHOR_SENTENCES = [s for group in NON_MEMORY_ANCHOR_GROUPS.values() for s in group]

# 6. 语义评分参数（Semantic Relevance Scoring）
# Strong Match: 与某条 Memory Prototype 的相似度超过此阈值时，直接用 max 值（而非 Top-K 平均）
STRONG_MATCH_THRESHOLD = 0.85
# Top-K: 取相似度前 K 条的平均值作为空间得分
TOP_K = 3
# Non-Memory 惩罚系数: final = memory_score - β × non_memory_score
NON_MEMORY_PENALTY = 0.5