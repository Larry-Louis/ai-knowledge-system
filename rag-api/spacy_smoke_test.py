from __future__ import annotations

import argparse
import json
import time

from infrastructure.nlp.spacy_information_density import SpaCyInformationRichnessAnalyzer


SAMPLES = [
    "我最近一直在研究Adaptive AUTOSAR，准备把公司的通信模块在2026-07-15前迁移到ARA::COM，目标是把延迟从120ms降到80ms。",
    "我们团队正在用Python和Qdrant做分布式RAG系统，包含embedding服务、向量检索API和异步任务队列。",
    "我喜欢古典音乐，尤其是巴赫和肖邦。",
    "今天心情不错，先这样吧。",
    "刚才不算，开玩笑的。",
    "Plan: migrate service A to service B, add Redis cache, expected p95 latency < 150ms.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="spaCy information richness smoke test")
    parser.add_argument("--text", default="", help="Analyze one custom sentence")
    args = parser.parse_args()

    analyzer = SpaCyInformationRichnessAnalyzer()

    load_t0 = time.perf_counter()
    available = analyzer.available
    load_seconds = time.perf_counter() - load_t0

    print("== spaCy Smoke Test ==")
    print("backend=spacy+entity_ruler")
    print(f"model_available={available}")
    print(f"model_probe_seconds={load_seconds:.3f}")
    print()

    if args.text.strip():
        t0 = time.perf_counter()
        entities_by_label = analyzer.group_entities_by_label(args.text)
        result = analyzer.analyze(args.text)
        elapsed = time.perf_counter() - t0

        output = {
            "mode": "single",
            "text": args.text,
            "score": round(result.score, 4),
            "evidence": result.evidence,
            "entities_by_label": entities_by_label,
            "entity_sample": result.meta.get("entity_sample", []),
            "model_available": result.meta.get("model_available"),
            "model_load_error": result.meta.get("model_load_error"),
            "elapsed_seconds": round(elapsed, 4),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    for idx, text in enumerate(SAMPLES, start=1):
        t0 = time.perf_counter()
        result = analyzer.analyze(text)
        elapsed = time.perf_counter() - t0

        output = {
            "index": idx,
            "text": text,
            "score": round(result.score, 4),
            "evidence": result.evidence,
            "entities_by_label": result.meta.get("entities_by_label", {}),
            "entity_sample": result.meta.get("entity_sample", []),
            "model_available": result.meta.get("model_available"),
            "elapsed_seconds": round(elapsed, 4),
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
