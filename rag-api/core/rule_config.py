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
DOMAIN_ACTIONS = {"修复", "部署", "创建", "调研", "优化", "检索"}
# DOMAIN_OBJECTS: 特定于系统业务领域的实体/对象。
DOMAIN_OBJECTS = {"接口", "逻辑", "知识库", "检索", "模型", "代码", "API"}
# 同时匹配到两者将显著提高置信度评分。
