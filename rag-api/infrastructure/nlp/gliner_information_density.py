from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

try:
    from infrastructure.logging.logger import pipeline_logger as _logger
except Exception:  # pragma: no cover - fallback for standalone script execution
    import logging

    _logger = logging.getLogger("gliner_information_density")


@dataclass
class InformationRichnessResult:
    score: float
    evidence: dict[str, int]
    meta: dict[str, Any]


class GLiNERInformationRichnessAnalyzer:
    """Information Richness analyzer aligned with docs/rule-score specs.

    This module is intentionally independent from rule_evaluator.py.
    """

    DEFAULT_LABELS = [
        "Person",
        "Location",
        "Organization",
        "Product",
        "Brand",
        "Movie",
        "Book",
        "Game",
        "Software",
        "Technology",
        "Framework",
        "Programming Language",
        "AI Model",
        "Library",
        "API",
        "Repository",
        "Version",
        "Tool",
    ]

    _NUMBER_PATTERNS = [
        re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
        re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
        re.compile(r"\b\d+(\.\d+)?%\b"),
        re.compile(r"\b\d+(\.\d+)?\b"),
        re.compile(r"\b\$\d+(\.\d+)?\b"),
        re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|min|h|km|m|gb|mb|tb|k)\b", re.IGNORECASE),
    ]

    _RELATION_PATTERNS = [
        re.compile(r"(我的|我们|我负责|我参与|我主导|我在|我所属|团队|公司|项目)")
    ]

    _ATTRIBUTE_PATTERNS = [
        re.compile(r"[\u4e00-\u9fa5]{1,4}(色|款|版|型|级|类|风格|方案|版本)"),
        re.compile(r"\b(large|small|high|low|fast|slow|wireless|hybrid|distributed)\b", re.IGNORECASE),
    ]

    _STRUCTURE_PATTERNS = [
        re.compile(r"(例如|比如|包括|包括但不限于|如下|第一|第二|第三|因为|所以|因此|但是|而且|并且|另外|同时|对比|相比)"),
        re.compile(r"[,，;；:：]\s*"),
    ]

    _NOUN_PHRASE_PATTERNS = [
        re.compile(r"[\u4e00-\u9fa5]{2,12}(系统|模块|方案|架构|模型|项目|接口|服务|数据库|框架|算法|工具|流程)"),
        re.compile(r"\b[A-Za-z][A-Za-z0-9_.-]{1,30}\s+(system|module|service|model|framework|library|api|pipeline|database)\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        model_name: str = "urchade/gliner_base",
        labels: list[str] | None = None,
        threshold: float = 0.45,
    ) -> None:
        self.model_name = model_name
        self.labels = labels or self.DEFAULT_LABELS
        self.threshold = threshold
        self._model: Any | None = None
        self._load_error: str | None = None
        self._model_load_seconds: float | None = None

    @property
    def available(self) -> bool:
        if self._model is not None:
            return True
        self._ensure_model_loaded()
        return self._model is not None

    def _ensure_model_loaded(self) -> None:
        if self._model is not None or self._load_error is not None:
            return

        started = time.perf_counter()
        try:
            from gliner import GLiNER  # type: ignore

            self._model = GLiNER.from_pretrained(self.model_name)
            self._model_load_seconds = time.perf_counter() - started
            _logger.info(
                "gliner_information_density: model_loaded model=%s elapsed=%.3fs",
                self.model_name,
                self._model_load_seconds,
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            self._load_error = str(exc)
            self._model_load_seconds = time.perf_counter() - started
            _logger.warning(
                "gliner_information_density: model_load_failed model=%s elapsed=%.3fs error=%s",
                self.model_name,
                self._model_load_seconds,
                self._load_error,
            )

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        if not text.strip():
            return []

        self._ensure_model_loaded()
        if self._model is None:
            return []

        try:
            entities = self._model.predict_entities(
                text,
                self.labels,
                threshold=self.threshold,
            )
            return [e for e in entities if (e.get("text") or "").strip()]
        except TypeError:
            # Compatibility fallback for some GLiNER signatures.
            entities = self._model.predict_entities(text, self.labels)
            normalized = []
            for e in entities:
                if (e.get("text") or "").strip() and e.get("score", 1.0) >= self.threshold:
                    normalized.append(e)
            return normalized
        except Exception as exc:  # pragma: no cover - environment dependent
            _logger.warning("gliner_information_density: entity_predict_failed error=%s", exc)
            return []

    def analyze(self, text: str) -> InformationRichnessResult:
        source = text or ""
        entities = self.extract_entities(source)
        entities_by_label = self.group_entities_by_label_from_entities(entities)

        evidence = {
            "named_objects": self._count_named_objects(entities),
            "noun_phrases": self._count_noun_phrases(source),
            "numbers": self._count_numbers(source),
            "relations": self._count_relations(source),
            "attributes": self._count_attributes(source),
            "structure": self._count_structure(source),
        }

        score = self._compute_score(evidence)
        meta = {
            "model_name": self.model_name,
            "threshold": self.threshold,
            "model_available": self._model is not None,
            "model_load_error": self._load_error,
            "model_load_seconds": self._model_load_seconds,
            "entity_sample": entities[:5],
            "entities_by_label": entities_by_label,
        }

        _logger.info(
            "gliner_information_density: score=%.4f evidence=%s available=%s",
            score,
            evidence,
            meta["model_available"],
        )
        return InformationRichnessResult(score=score, evidence=evidence, meta=meta)

    @staticmethod
    def _count_named_objects(entities: list[dict[str, Any]]) -> int:
        unique = set()
        for entity in entities:
            text = (entity.get("text") or "").strip().lower()
            if text:
                unique.add(text)
        return len(unique)

    def group_entities_by_label(self, text: str) -> dict[str, list[str]]:
        """Group GLiNER entity extraction result by label for manual testing."""
        entities = self.extract_entities(text)
        return self.group_entities_by_label_from_entities(entities)

    @staticmethod
    def group_entities_by_label_from_entities(entities: list[dict[str, Any]]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        dedup: dict[str, set[str]] = {}

        for entity in entities:
            label = str(entity.get("label") or "Unknown")
            entity_text = (entity.get("text") or "").strip()
            if not entity_text:
                continue

            if label not in grouped:
                grouped[label] = []
                dedup[label] = set()

            normalized = entity_text.lower()
            if normalized in dedup[label]:
                continue

            dedup[label].add(normalized)
            grouped[label].append(entity_text)

        return grouped

    def _count_noun_phrases(self, text: str) -> int:
        phrases: set[str] = set()
        for pattern in self._NOUN_PHRASE_PATTERNS:
            phrases.update(m.group(0).strip().lower() for m in pattern.finditer(text))
        return len(phrases)

    def _count_numbers(self, text: str) -> int:
        hits: set[str] = set()
        for pattern in self._NUMBER_PATTERNS:
            hits.update(m.group(0) for m in pattern.finditer(text))
        return len(hits)

    def _count_relations(self, text: str) -> int:
        return sum(len(pattern.findall(text)) for pattern in self._RELATION_PATTERNS)

    def _count_attributes(self, text: str) -> int:
        return sum(len(pattern.findall(text)) for pattern in self._ATTRIBUTE_PATTERNS)

    def _count_structure(self, text: str) -> int:
        sentence_count = max(1, len([s for s in re.split(r"[。！？!?\n]", text) if s.strip()]))
        structure_hits = 0
        for pattern in self._STRUCTURE_PATTERNS:
            structure_hits += len(pattern.findall(text))
        if sentence_count >= 2:
            structure_hits += 1
        return structure_hits

    @staticmethod
    def _compute_score(evidence: dict[str, int]) -> float:
        # Cap each feature to avoid domination by long text.
        caps = {
            "named_objects": 6,
            "noun_phrases": 8,
            "numbers": 6,
            "relations": 5,
            "attributes": 6,
            "structure": 6,
        }
        weights = {
            "named_objects": 0.25,
            "noun_phrases": 0.20,
            "numbers": 0.15,
            "relations": 0.15,
            "attributes": 0.10,
            "structure": 0.15,
        }

        normalized = 0.0
        for key, value in evidence.items():
            cap = caps[key]
            normalized += weights[key] * min(value, cap) / cap
        return max(0.0, min(1.0, normalized))


def analyze_information_richness(
    text: str,
    model_name: str = "urchade/gliner_base",
    threshold: float = 0.45,
) -> InformationRichnessResult:
    analyzer = GLiNERInformationRichnessAnalyzer(model_name=model_name, threshold=threshold)
    return analyzer.analyze(text)
