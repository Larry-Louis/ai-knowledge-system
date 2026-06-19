# Configuration for Rule-based Filtering (Rule Score)
# These settings allow fine-tuning the heuristic filtering without touching core logic.

# 1. Probe Structure Settings
# INSTRUCTION_KEYWORDS: List of keywords that signal a user wants to perform a specific action/task.
INSTRUCTION_KEYWORDS = [
    "修改", "创建", "优化", "修复", "总结", "解释", "分析", 
    "帮我", "部署", "查询", "检索"
]
# CODE_BLOCK_SCORE: Added to the score if ``` is present, indicating technical content.
CODE_BLOCK_SCORE = 0.2
# LENGTH_MIN/MAX: Bounds to filter out noise; only applied to user inputs.
LENGTH_MIN = 10
LENGTH_MAX = 500
# LENGTH_SCORE: Points added if the user input length is within the specified bounds.
LENGTH_SCORE = 0.2

# 2. Polarity Filter Settings
POSITIVE_WORDS = {"好", "支持", "推荐", "可以", "需要", "搞定"}
NEGATIVE_WORDS = {"拒绝", "反对", "不行", "出错", "bug", "失败"}
DISSOLVE_WORDS = {"刚才不算", "开玩笑的", "手抖了"}

# 3. Domain Pattern Matcher Settings
# DOMAIN_ACTIONS: Actions specific to the system's operational domain.
DOMAIN_ACTIONS = {"修复", "部署", "创建", "调研", "优化", "检索"}
# DOMAIN_OBJECTS: Entities/objects specific to the system's operational domain.
DOMAIN_OBJECTS = {"接口", "逻辑", "知识库", "检索", "模型", "代码", "API"}
# Matching both increases the confidence score significantly.
