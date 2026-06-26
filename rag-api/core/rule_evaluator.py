import re
import rule_config
from core.logger import pipeline_logger
from services.embedding import EmbeddingService
from core.math_utils import cosine_similarity

def probe_structure_score(text: str, is_user_turn: bool = True) -> float:
    score = rule_config.ORIGINAL_SCORE
    
    if any(k in text for k in rule_config.INSTRUCTION_KEYWORDS):
        score += rule_config.INSTRUCTION_KEYWORDS_SCORE
    pipeline_logger.info(f"probe_structure_score: instruction_keywords_score={rule_config.INSTRUCTION_KEYWORDS_SCORE if any(k in text for k in rule_config.INSTRUCTION_KEYWORDS) else 0.0}")
        
    # 代码块通常意味着技术任务，重要性高
    if '```' in text:
        score += rule_config.CODE_BLOCK_SCORE
    pipeline_logger.info(f"probe_structure_score: code_block_score={rule_config.CODE_BLOCK_SCORE if '```' in text else 0.0}")
        
    if is_user_turn:
        length = len(text)
        if not (rule_config.LENGTH_MIN < length < rule_config.LENGTH_MAX):
            score -= rule_config.LENGTH_SCORE
            pipeline_logger.info(f"probe_structure_score: length_score_adjustment={-rule_config.LENGTH_SCORE}")
        else:
            pipeline_logger.info("probe_structure_score: length_score_adjustment=0.0")
            
    return min(score, 1.0)

def detect_polarity_score(text: str) -> float:
    # 存在消解词，直接打回
    if any(w in text for w in rule_config.DISSOLVE_WORDS):
        pipeline_logger.info("detect_polarity_score: dissolve_words_found=-0.5")
        return -0.5
    
    pos = sum(1 for w in rule_config.POSITIVE_WORDS if w in text)
    neg = sum(1 for w in rule_config.NEGATIVE_WORDS if w in text)
    
    # 倾向计算
    if pos > neg: 
        pipeline_logger.info("detect_polarity_score: positive=0.2")
        return 0.2
    if neg > pos: 
        pipeline_logger.info("detect_polarity_score: negative=-0.2")
        return -0.2
    pipeline_logger.info("detect_polarity_score: neutral=0.0")
    return 0.0

ANCHOR_SENTENCES = [
    "我在做一个项目",
    "我们团队正在开发",
    "我的工作是",
    "我打算做这件事",
    "我计划下一步",
    "我喜欢这个东西",
    "我不喜欢这个",
    "我擅长这方面",
    "我不太会这个",
    "我遇到了一个问题",
    "我最近在学习",
]
_anchor_vectors: list[list[float]] | None = None

def _get_anchor_vectors() -> list[list[float]]:
    global _anchor_vectors
    if _anchor_vectors is None:
        _anchor_vectors = [EmbeddingService.embed(s) for s in ANCHOR_SENTENCES]
    return _anchor_vectors

def semantic_relevance_score(user_text: str) -> float:
    vec = EmbeddingService.embed(user_text)
    return max(cosine_similarity(vec, a) for a in _get_anchor_vectors())

def match_domain_pattern(text: str) -> float:
    action_hit = any(act in text for act in rule_config.DOMAIN_ACTIONS)
    object_hit = any(obj in text for obj in rule_config.DOMAIN_OBJECTS)
    
    rule_score = 0.0
    if action_hit and object_hit: rule_score = 0.6
    elif action_hit or object_hit: rule_score = 0.2
    
    sem_score = semantic_relevance_score(text)
    
    final_score = max(rule_score, sem_score * 0.8)
    pipeline_logger.info(f"match_domain_pattern: rule_score={rule_score}, sem_score={sem_score}, final={final_score}")
    return final_score

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