import re
from core import rule_config
from core.logger import pipeline_logger

def probe_structure_score(text: str, is_user_turn: bool = True) -> float:
    score = rule_config.ORIGINAL_SCORE
    
    # 任务通常包含特定的指令词
    if any(k in text for k in rule_config.INSTRUCTION_KEYWORDS):
        score += rule_config.INSTRUCTION_KEYWORDS_SCORE
        
    # 代码块通常意味着技术任务，重要性高
    if '```' in text:
        score += rule_config.CODE_BLOCK_SCORE
        
    # 长度判定：仅针对用户输入判断，AI回复通常较长
    if is_user_turn:
        length = len(text)
        if not (rule_config.LENGTH_MIN < length < rule_config.LENGTH_MAX):
            score -= rule_config.LENGTH_SCORE
            
    return min(score, 1.0)

def detect_polarity_score(text: str) -> float:
    # 存在消解词，直接打回
    if any(w in text for w in rule_config.DISSOLVE_WORDS):
        return -0.5
    
    pos = sum(1 for w in rule_config.POSITIVE_WORDS if w in text)
    neg = sum(1 for w in rule_config.NEGATIVE_WORDS if w in text)
    
    # 倾向计算
    if pos > neg: return 0.2
    if neg > pos: return -0.2
    return 0.0

def match_domain_pattern(text: str) -> float:
    action_hit = any(act in text for act in rule_config.DOMAIN_ACTIONS)
    object_hit = any(obj in text for obj in rule_config.DOMAIN_OBJECTS)
    
    if action_hit and object_hit:
        return 0.6  # 动宾明确
    if action_hit or object_hit:
        return 0.2  # 单侧命中
    return 0.0

def calculate_rule_score(text: str, turn_text: str = None, is_user_turn: bool = True) -> float:
    # 综合得分
    if turn_text is None:
        turn_text = text
    pss = probe_structure_score(text, is_user_turn)
    dps = detect_polarity_score(turn_text)
    mdp = match_domain_pattern(turn_text)
    score = pss + dps + mdp
    pipeline_logger.debug(f"calculate_rule_score: probe_structure={pss}, detect_polarity={dps}, match_domain={mdp}, total={score}")
    return max(0.0, min(1.0, score))
