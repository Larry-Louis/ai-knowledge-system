from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

try:
    import spacy
    from spacy.language import Language
    from spacy.pipeline import EntityRuler
except Exception:  # pragma: no cover - optional dependency
    spacy = None
    Language = Any
    EntityRuler = Any

try:
    from infrastructure.logging.logger import pipeline_logger as _logger
except Exception:  # pragma: no cover - fallback for standalone script execution
    import logging

    _logger = logging.getLogger("spacy_information_density")


@dataclass
class InformationRichnessResult:
    score: float
    evidence: dict[str, int]
    meta: dict[str, Any]


class SpaCyInformationRichnessAnalyzer:
    """Lightweight Information Richness analyzer using spaCy + EntityRuler.

    This prototype is independent from rule_evaluator.py and intended for A/B testing
    against GLiNER with lower dependency/runtime cost.
    """

    DEFAULT_LABELS = [
        "Programming Language",
        "Framework",
        "API",
        "Library",
        "Tool",
        "Software",
        "Version",
        "Organization",
        "Product",
    ]

    _DEFAULT_ENTITY_PATTERNS: list[dict[str, Any]] = [
        {"label": "Programming Language", "pattern": "Python"},
        {"label": "Programming Language", "pattern": "Java"},
        {"label": "Programming Language", "pattern": "JavaScript"},
        {"label": "Programming Language", "pattern": "TypeScript"},
        {"label": "Programming Language", "pattern": "Go"},
        {"label": "Programming Language", "pattern": "Rust"},
        {"label": "Framework", "pattern": "FastAPI"},
        {"label": "Framework", "pattern": "Django"},
        {"label": "Framework", "pattern": "Flask"},
        {"label": "Framework", "pattern": "Spring Boot"},
        {"label": "Framework", "pattern": "React"},
        {"label": "Framework", "pattern": "Vue"},
        {"label": "API", "pattern": "OpenAI API"},
        {"label": "API", "pattern": "Azure OpenAI"},
        {"label": "API", "pattern": "Qdrant"},
        {"label": "API", "pattern": "REST API"},
        {"label": "Library", "pattern": "NumPy"},
        {"label": "Library", "pattern": "Pandas"},
        {"label": "Library", "pattern": "Transformers"},
        {"label": "Library", "pattern": "LangChain"},
        {"label": "Tool", "pattern": "Docker"},
        {"label": "Tool", "pattern": "Kubernetes"},
        {"label": "Tool", "pattern": "Redis"},
        {"label": "Tool", "pattern": "SQLite"},
        {"label": "Tool", "pattern": "PostgreSQL"},
        {"label": "Software", "pattern": "RAG"},
        {"label": "Software", "pattern": "Adaptive AUTOSAR"},
        {"label": "Software", "pattern": "ARA::COM"},
    ]

    _NUMBER_PATTERNS = [
        re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
        re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
        re.compile(r"\b\d+(\.\d+)?%\b"),
        re.compile(r"\bv?\d+(\.\d+)+\b", re.IGNORECASE),
        re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|min|h|km|m|gb|mb|tb|k)\b", re.IGNORECASE),
        re.compile(r"\b\d+(\.\d+)?\b"),
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
        re.compile(r"\b[A-Za-z][A-Za-z0-9_.:-]{1,30}\s+(system|module|service|model|framework|library|api|pipeline|database)\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        labels: list[str] | None = None,
        custom_patterns: list[dict[str, Any]] | None = None,
    ) -> None:
        self.labels = labels or self.DEFAULT_LABELS
        self.custom_patterns = custom_patterns or []
        self._nlp: Language | None = None
        self._load_error: str | None = None
        self._model_load_seconds: float | None = None
        merged_patterns = list(self._DEFAULT_ENTITY_PATTERNS)
        merged_patterns.extend(self.custom_patterns)
        self._label_lookup: dict[str, str] = {}
        for item in merged_patterns:
            text = str(item.get("pattern") or "").strip()
            label = str(item.get("label") or "Unknown")
            if text and label:
                self._label_lookup[text.lower()] = label

    @property
    def available(self) -> bool:
        if self._nlp is not None:
            return True
        self._ensure_pipeline_loaded()
        return self._nlp is not None

    def _ensure_pipeline_loaded(self) -> None:
        if self._nlp is not None or self._load_error is not None:
            return

        started = time.perf_counter()
        try:
            if spacy is None:
                raise RuntimeError("spaCy is not installed")

            # Use a blank multilingual pipeline to avoid downloading large models.
            nlp = spacy.blank("xx")
            ruler = nlp.add_pipe("entity_ruler")
            assert isinstance(ruler, EntityRuler)

            patterns = list(self._DEFAULT_ENTITY_PATTERNS)
            patterns.extend(self.custom_patterns)
            if patterns:
                ruler.add_patterns(patterns)

            self._nlp = nlp
            self._model_load_seconds = time.perf_counter() - started
            _logger.info(
                "spacy_information_density: pipeline_loaded elapsed=%.3fs patterns=%d",
                self._model_load_seconds,
                len(patterns),
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            self._load_error = str(exc)
            self._model_load_seconds = time.perf_counter() - started
            _logger.warning(
                "spacy_information_density: pipeline_load_failed elapsed=%.3fs error=%s",
                self._model_load_seconds,
                self._load_error,
            )

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        if not text.strip():
            return []

        self._ensure_pipeline_loaded()
        if self._nlp is None:
            return []

        doc = self._nlp(text)
        entities: list[dict[str, Any]] = []

        for ent in doc.ents:
            if self.labels and ent.label_ not in self.labels:
                continue
            entities.append(
                {
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "text": ent.text,
                    "label": ent.label_,
                    "score": 1.0,
                }
            )

        for match in re.finditer(r"\bv?\d+(\.\d+)+\b", text, flags=re.IGNORECASE):
            entities.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "text": match.group(0),
                    "label": "Version",
                    "score": 1.0,
                }
            )

        # Fallback for mixed-language technical terms that can be missed by token boundaries.
        for term, label in self._label_lookup.items():
            if re.fullmatch(r"[A-Za-z0-9_.:+#-]+", term):
                pattern = rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"
            else:
                pattern = re.escape(term)
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                entities.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "text": text[match.start():match.end()],
                        "label": label,
                        "score": 0.95,
                    }
                )

        return self._deduplicate_entities(entities)

    def analyze(self, text: str) -> InformationRichnessResult:
        source = text or ""
        entities = self.extract_entities(source)
        named_object_texts = self._extract_named_object_texts(entities)
        named_object_count = len(named_object_texts)
        entities_by_label = self.group_entities_by_label_from_entities(entities)

        evidence = {
            # Keep scoring anchored on stable entity texts rather than label correctness.
            "named_objects": named_object_count,
            "noun_phrases": self._count_noun_phrases(source),
            "numbers": self._count_numbers(source),
            "relations": self._count_relations(source),
            "attributes": self._count_attributes(source),
            "structure": self._count_structure(source),
        }

        score = self._compute_score(evidence)
        meta = {
            "backend": "spacy",
            "model_available": self._nlp is not None,
            "model_load_error": self._load_error,
            "model_load_seconds": self._model_load_seconds,
            "entity_sample": entities[:5],
            "named_object_texts": named_object_texts,
            "entity_coverage": self._entity_coverage(named_object_count),
            "entities_by_label": entities_by_label,
        }

        _logger.info(
            "spacy_information_density: score=%.4f evidence=%s available=%s",
            score,
            evidence,
            meta["model_available"],
        )
        return InformationRichnessResult(score=score, evidence=evidence, meta=meta)

    def group_entities_by_label(self, text: str) -> dict[str, list[str]]:
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

    @staticmethod
    def _deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Prefer longer spans first so that "Azure OpenAI API" wins over its subspans.
        entities = sorted(
            entities,
            key=lambda item: (
                int(item.get("end", -1)) - int(item.get("start", -1)),
                float(item.get("score", 0.0)),
            ),
            reverse=True,
        )

        dedup: set[tuple[str, str, int, int]] = set()
        occupied: list[tuple[int, int]] = []
        kept: list[dict[str, Any]] = []
        for item in entities:
            start = int(item.get("start", -1))
            end = int(item.get("end", -1))
            if start >= 0 and end >= 0:
                # If there is any span overlap, keep the earlier (longer/higher-score) one.
                if any(start < e and end > s for s, e in occupied):
                    continue

            key = (
                # Weak-label strategy: dedup is anchored on text/span, not label identity.
                "_",
                (item.get("text") or "").strip().lower(),
                start,
                end,
            )
            if key in dedup:
                continue
            dedup.add(key)
            kept.append(item)
            if start >= 0 and end >= 0:
                occupied.append((start, end))
        return kept

    @staticmethod
    def _count_named_objects(entities: list[dict[str, Any]]) -> int:
        unique = set()
        for entity in entities:
            text = (entity.get("text") or "").strip().lower()
            if text:
                unique.add(text)
        return len(unique)

    @staticmethod
    def _extract_named_object_texts(entities: list[dict[str, Any]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for entity in entities:
            text = (entity.get("text") or "").strip()
            if not text:
                continue
            normalized = text.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(text)
        return ordered

    @staticmethod
    def _entity_coverage(named_object_count: int) -> float:
        # Saturates quickly: 0 entity -> 0.0, >=6 entities -> 1.0.
        return max(0.0, min(1.0, named_object_count / 6.0))

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


def analyze_information_richness(text: str) -> InformationRichnessResult:
    analyzer = SpaCyInformationRichnessAnalyzer()
    return analyzer.analyze(text)
