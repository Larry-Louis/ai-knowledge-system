"""NLP helper modules for lightweight memory scoring extensions."""

from __future__ import annotations

from typing import Any

from infrastructure.nlp.spacy_information_density import (
	InformationRichnessResult,
	SpaCyInformationRichnessAnalyzer,
)

_spacy_analyzer: SpaCyInformationRichnessAnalyzer | None = None


def get_information_density_analyzer() -> SpaCyInformationRichnessAnalyzer:
	"""Return a singleton analyzer for information density extraction."""
	global _spacy_analyzer
	if _spacy_analyzer is None:
		_spacy_analyzer = SpaCyInformationRichnessAnalyzer()
	return _spacy_analyzer


def evaluate_information_density(text: str) -> InformationRichnessResult:
	"""Core API for information density scoring based on entity-rich signals."""
	analyzer = get_information_density_analyzer()
	return analyzer.analyze(text)


__all__ = [
	"InformationRichnessResult",
	"SpaCyInformationRichnessAnalyzer",
	"evaluate_information_density",
	"get_information_density_analyzer",
]
