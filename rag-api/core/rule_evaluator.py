import re
import rule_config
from core.logger import pipeline_logger
from services.embedding import EmbeddingService
from core.math_utils import cosine_similarity


def probe_structure_score(text: str, is_user_turn: bool = True) -> float:
    score = rule_config.ORIGINAL_SCORE

    if any(k in text for k in rule_config.INSTRUCTION_KEYWORDS):
        score += rule_config.INSTRUCTION_KEYWORDS_SCORE
    pipeline_logger.info(
        f"probe_structure_score: instruction_keywords_score="
        f"{rule_config.INSTRUCTION_KEYWORDS_SCORE if any(k in text for k in rule_config.INSTRUCTION_KEYWORDS) else 0.0}"
    )

    if '```' in text:
        score += rule_config.CODE_BLOCK_SCORE
    pipeline_logger.info(
        f"probe_structure_score: code_block_score="
        f"{rule_config.CODE_BLOCK_SCORE if '```' in text else 0.0}"
    )

    if is_user_turn:
        length = len(text)
        if not (rule_config.LENGTH_MIN < length < rule_config.LENGTH_MAX):
            score -= rule_config.LENGTH_SCORE
            pipeline_logger.info(f"probe_structure_score: length_score_adjustment={-rule_config.LENGTH_SCORE}")
        else:
            pipeline_logger.info("probe_structure_score: length_score_adjustment=0.0")

    return min(score, 1.0)


def detect_polarity_score(text: str) -> float:
    if any(w in text for w in rule_config.DISSOLVE_WORDS):
        pipeline_logger.info("detect_polarity_score: dissolve_words_found=-0.5")
        return -0.5

    pos = sum(1 for w in rule_config.POSITIVE_WORDS if w in text)
    neg = sum(1 for w in rule_config.NEGATIVE_WORDS if w in text)

    if pos > neg:
        pipeline_logger.info("detect_polarity_score: positive=0.2")
        return 0.2
    if neg > pos:
        pipeline_logger.info("detect_polarity_score: negative=-0.2")
        return -0.2
    pipeline_logger.info("detect_polarity_score: neutral=0.0")
    return 0.0


# ============================================================
# 语义评分核心
# ============================================================

def _top_k_average(vec: list[float], anchor_vectors: list[list[float]], k: int) -> tuple[float, float]:
    """
    计算 Top-K 平均相似度和最大相似度

    边缘保护:
      1. 空列表 → (0.0, 0.0)
      2. K 自适应 — 若 k > len(vectors) 取 min(k, len)
      3. O(n log n) 对 <30 条可忽略
    """
    if not anchor_vectors:
        return 0.0, 0.0

    sims = [cosine_similarity(vec, a) for a in anchor_vectors]
    sims.sort(reverse=True)
    effective_k = min(k, len(sims))
    top_k = sims[:effective_k]
    return sum(top_k) / effective_k, sims[0]


# ---- 缓存：扁平 Memory Prototype 向量（保留向后兼容） ----
_anchor_vectors: list[list[float]] | None = None

def _get_anchor_vectors() -> list[list[float]]:
    global _anchor_vectors
    if _anchor_vectors is None:
        _anchor_vectors = [EmbeddingService.embed(s) for s in rule_config.ANCHOR_SENTENCES]
    return _anchor_vectors


# ---- 缓存：分组 Memory Prototype 数据（句子+向量） ----
_grouped_anchor_data: dict[str, list[tuple[str, list[float]]]] | None = None

def _get_grouped_anchor_data() -> dict[str, list[tuple[str, list[float]]]]:
    global _grouped_anchor_data
    if _grouped_anchor_data is None:
        _grouped_anchor_data = {
            group: [(s, EmbeddingService.embed(s)) for s in sentences]
            for group, sentences in rule_config.ANCHOR_GROUPS.items()
        }
    return _grouped_anchor_data


# ---- 缓存：Non-Memory Prototype 向量（扁平，保持向后兼容） ----
_non_memory_anchor_vectors: list[list[float]] | None = None

def _get_non_memory_anchor_vectors() -> list[list[float]]:
    global _non_memory_anchor_vectors
    if _non_memory_anchor_vectors is None:
        _non_memory_anchor_vectors = [
            EmbeddingService.embed(s) for s in rule_config.NON_MEMORY_ANCHOR_SENTENCES
        ]
    return _non_memory_anchor_vectors


# ---- 缓存：分组 Non-Memory Prototype 数据（句子+向量） ----
_non_memory_grouped_data: dict[str, list[tuple[str, list[float]]]] | None = None

def _get_non_memory_grouped_data() -> dict[str, list[tuple[str, list[float]]]]:
    global _non_memory_grouped_data
    if _non_memory_grouped_data is None:
        _non_memory_grouped_data = {
            group: [(s, EmbeddingService.embed(s)) for s in sentences]
            for group, sentences in rule_config.NON_MEMORY_ANCHOR_GROUPS.items()
        }
    return _non_memory_grouped_data


def semantic_relevance_score(user_text: str) -> tuple[float, str]:
    """
    双原型空间语义评分 + 分组最优语义方向 + 最佳匹配句子追踪

    流程:
      1. Memory Space: 对 ANCHOR_GROUPS 每组分别计算 Top-K 平均
         若某组 max_sim > STRONG_MATCH_THRESHOLD 则直接用 max
         取最高分组得分作为 memory_score，对应组为 best_group
      2. Non-Memory Space: 扁平 Top-K 平均 → non_memory_score
      3. final = memory_score - beta * non_memory_score

    Returns:
        (semantic_score, best_group)
    """
    vec = EmbeddingService.embed(user_text)

    # ---- Memory Space：分组评分 + 追踪最佳句子 ----
    grouped_data = _get_grouped_anchor_data()
    best_group = "General"
    best_group_score = 0.0
    best_sentence_text = ""

    for group_name, items in grouped_data.items():
        if not items:
            continue

        sent_vec_pairs = [(s, cosine_similarity(vec, v)) for s, v in items]
        sims = [sim for _, sim in sent_vec_pairs]
        sims.sort(reverse=True)
        effective_k = min(rule_config.TOP_K, len(sims))
        avg = sum(sims[:effective_k]) / effective_k
        max_sim = sims[0]

        group_score = max_sim if max_sim > rule_config.STRONG_MATCH_THRESHOLD else avg

        if group_score > best_group_score:
            best_group_score = group_score
            best_group = group_name
            best_sent, _ = max(sent_vec_pairs, key=lambda x: x[1])
            best_sentence_text = best_sent

    memory_score = best_group_score

    # ---- Non-Memory Space：分组评分 + 追踪最佳句子 ----
    non_mem_grouped_data = _get_non_memory_grouped_data()
    best_non_mem_group = "None"
    best_non_mem_score = 0.0
    best_non_mem_sentence = ""

    for group_name, items in non_mem_grouped_data.items():
        if not items:
            continue

        sent_vec_pairs = [(s, cosine_similarity(vec, v)) for s, v in items]
        sims = [sim for _, sim in sent_vec_pairs]
        sims.sort(reverse=True)
        effective_k = min(rule_config.TOP_K, len(sims))
        avg = sum(sims[:effective_k]) / effective_k
        max_sim = sims[0]

        group_score = max_sim if max_sim > rule_config.STRONG_MATCH_THRESHOLD else avg

        if group_score > best_non_mem_score:
            best_non_mem_score = group_score
            best_non_mem_group = group_name
            best_non_mem_sentence = max(sent_vec_pairs, key=lambda x: x[1])[0]

    non_memory_score = best_non_mem_score

    semantic_score = memory_score - rule_config.NON_MEMORY_PENALTY * non_memory_score

    pipeline_logger.info(
        f"semantic_relevance: "
        f"mem_group=\"{best_group}\"({best_group_score:.4f}), "
        f"mem_sentence=\"{best_sentence_text}\", "
        f"non_mem_group=\"{best_non_mem_group}\"({best_non_mem_score:.4f}), "
        f"non_mem_sentence=\"{best_non_mem_sentence}\", "
        f"final={semantic_score:.4f}"
    )
    return max(0.0, min(1.0, semantic_score)), best_group


def match_domain_pattern(text: str) -> tuple[float, str]:
    """
    领域模式匹配 + 语义相关性评分
    语义评分为基础，领域关键词匹配做乘算增益。

    Returns:
        (final_score, sem_group)
    """
    action_hit = any(act in text for act in rule_config.DOMAIN_ACTIONS)
    object_hit = any(obj in text for obj in rule_config.DOMAIN_OBJECTS)

    rule_score = 0.0
    if action_hit and object_hit:
        rule_score = 0.4
    elif action_hit or object_hit:
        rule_score = 0.15

    sem_score, sem_group = semantic_relevance_score(text)

    final_score = min(1.0, sem_score * (1 + rule_score))
    pipeline_logger.info(
        f"match_domain_pattern: rule_score={rule_score}, "
        f"sem_score={sem_score:.4f}, sem_group={sem_group}, "
        f"final={final_score:.4f}"
    )
    return final_score, sem_group


def calculate_rule_score(text: str, turn_text: str = "", is_user_turn: bool = True) -> tuple[float, str]:
    """综合评分入口，返回 (score, sem_direction)"""
    if turn_text is None:
        turn_text = text

    pss = probe_structure_score(text, is_user_turn)
    dps = detect_polarity_score(turn_text)
    mdp, mdp_sem_group = match_domain_pattern(text)

    score = pss + dps + mdp
    pipeline_logger.info(
        f"calculate_rule_score: sem_direction={mdp_sem_group}, "
        f"probe_structure={pss:.4f}, detect_polarity={dps:.4f}, "
        f"match_domain={mdp:.4f}, total={score:.4f}"
    )
    return max(0.0, min(1.0, score)), mdp_sem_group
