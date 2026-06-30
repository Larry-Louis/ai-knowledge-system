from __future__ import annotations

import argparse
import json
import time

from infrastructure.nlp.gliner_information_density import GLiNERInformationRichnessAnalyzer
from infrastructure.nlp.spacy_information_density import SpaCyInformationRichnessAnalyzer


def _flatten_entities_by_label(entities_by_label: dict[str, list[str]]) -> set[tuple[str, str]]:
    flattened: set[tuple[str, str]] = set()
    for label, values in entities_by_label.items():
        for value in values:
            flattened.add((label, value.strip().lower()))
    return flattened


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare GLiNER and spaCy backends")
    parser.add_argument("--text", required=True, help="Input sentence to compare")
    parser.add_argument(
        "--gliner-model",
        default="urchade/gliner_base",
        help="GLiNER model name or local path",
    )
    parser.add_argument("--gliner-threshold", type=float, default=0.45)
    args = parser.parse_args()

    text = args.text

    gliner = GLiNERInformationRichnessAnalyzer(
        model_name=args.gliner_model,
        threshold=args.gliner_threshold,
    )
    spacy_backend = SpaCyInformationRichnessAnalyzer()

    g_load_t0 = time.perf_counter()
    g_available = gliner.available
    g_load_elapsed = time.perf_counter() - g_load_t0

    s_load_t0 = time.perf_counter()
    s_available = spacy_backend.available
    s_load_elapsed = time.perf_counter() - s_load_t0

    g_t0 = time.perf_counter()
    g_result = gliner.analyze(text)
    g_elapsed = time.perf_counter() - g_t0

    s_t0 = time.perf_counter()
    s_result = spacy_backend.analyze(text)
    s_elapsed = time.perf_counter() - s_t0

    g_entities = g_result.meta.get("entities_by_label", {})
    s_entities = s_result.meta.get("entities_by_label", {})

    g_flat = _flatten_entities_by_label(g_entities)
    s_flat = _flatten_entities_by_label(s_entities)

    only_gliner = sorted([{"label": l, "text": t} for l, t in (g_flat - s_flat)], key=lambda x: (x["label"], x["text"]))
    only_spacy = sorted([{"label": l, "text": t} for l, t in (s_flat - g_flat)], key=lambda x: (x["label"], x["text"]))
    overlap = sorted([{"label": l, "text": t} for l, t in (g_flat & s_flat)], key=lambda x: (x["label"], x["text"]))

    output = {
        "text": text,
        "gliner": {
            "model": args.gliner_model,
            "available": g_available,
            "load_seconds": round(g_load_elapsed, 4),
            "infer_seconds": round(g_elapsed, 4),
            "score": round(g_result.score, 4),
            "named_objects": g_result.evidence.get("named_objects", 0),
            "entities_by_label": g_entities,
            "error": g_result.meta.get("model_load_error"),
        },
        "spacy": {
            "available": s_available,
            "load_seconds": round(s_load_elapsed, 4),
            "infer_seconds": round(s_elapsed, 4),
            "score": round(s_result.score, 4),
            "named_objects": s_result.evidence.get("named_objects", 0),
            "entities_by_label": s_entities,
            "error": s_result.meta.get("model_load_error"),
        },
        "diff": {
            "overlap": overlap,
            "only_gliner": only_gliner,
            "only_spacy": only_spacy,
        },
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
