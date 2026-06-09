#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
path = "F:/ai-knowledge-system/docs/phase1 spec.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

changes = []

# Line number fixes
replacements = {
    "memory_pipeline.py:538": "memory_pipeline.py:191",
    "memory_pipeline.py:498": "core/text_utils.py:68",
    "memory_pipeline.py:459": "core/decision_maker.py:17",
    "memory_pipeline.py:439": "core/text_utils.py:53",
    "memory_pipeline.py:88": "memory_pipeline.py:90",
}

for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)
        changes.append(old + " -> " + new)

# Function name fixes
func_fixes = {
    "_slm_validate": "slm_validate",
    "_classify_mu": "DecisionMaker.classify_mu",
    "_extract_mus": "extract_mus",
    "_normalize": "normalize",
    "_is_duplicate": "is_duplicate",
    "_detect_polarity": "detect_polarity",
}

for old, new in func_fixes.items():
    c = text.count(old)
    if c > 0:
        text = text.replace(old, new)
        changes.append(old + " -> " + new + " (" + str(c) + "x)")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("Changes made:")
for c in changes:
    print("  " + c)
print("File size:", len(text), "chars")
