"""Decision Maker for Memory Pipeline."""
from typing import Dict, Any

class DecisionMaker:
    IMPORTANCE_KEEP = 0.4
    IMPORTANCE_HIGH = 0.7
    CONFIDENCE_HIGH = 0.7

    TYPE_LAYER_MAP = {
        "ENTITY": "semantic",
        "RELATION": "semantic",
        "EVENT": "episodic",
        "TASK": "episodic",
    }

    @classmethod
    def classify_mu(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        [S1-4c] 应用重要性-置信度决策矩阵

        主要工作流：
        1. 从 SLM 验证结果中提取 importance 和 confidence 值（范围 0-1）
        2. 根据阈值判断是否保留 (keep)：
           - importance >= 0.4 时保留
           - importance >= 0.7 且 confidence >= 0.7 时标记为 "golden"
           - importance >= 0.7 时标记为 "review"
           - 否则标记为 "low"
        3. 根据 mu_type 映射到 layer_type（ENTITY/RELATION -> semantic, EVENT/TASK -> episodic）
        4. 返回包含 keep、type、tag、layer_type、importance、confidence、store_priority、summary 的字典
        """
        importance = max(0.0, min(1.0, result.get("importance", 0.0)))
        confidence = max(0.0, min(1.0, result.get("confidence", 0.0)))
        keep = importance >= cls.IMPORTANCE_KEEP

        # Decision matrix for stored items
        if keep and importance >= cls.IMPORTANCE_HIGH and confidence >= cls.CONFIDENCE_HIGH:
            store_priority = "golden"
        elif keep and importance >= cls.IMPORTANCE_HIGH:
            store_priority = "review"
        elif keep:
            store_priority = "low"
        else:
            store_priority = "drop"

        mu_type = result.get("type", "ENTITY")
        tag = result.get("tag", "noise")

        raw_summaries = result.get("summaries", [])
        if isinstance(raw_summaries, list) and len(raw_summaries) > 0:
            summaries = [s.strip() for s in raw_summaries if s and s.strip()]
        else:
            s = (result.get("summary") or "").strip()
            summaries = [s] if s else []

        return {
            "keep": keep and store_priority != "drop",
            "type": mu_type,
            "tag": tag,
            "layer_type": cls.TYPE_LAYER_MAP.get(mu_type, "semantic"),
            "importance": importance,
            "confidence": confidence,
            "store_priority": store_priority,
            "summary": summaries[0] if summaries else "",
            "summaries": summaries,
        }

