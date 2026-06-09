#!/usr/bin/env python3
"""Reconstruct phase1 spec v2.0 with proper UTF-8 encoding."""
import subprocess

# Get the corrupted v2.0 to extract ASCII structure
raw = subprocess.run(['git', 'cat-file', '-p', '239c190:docs/phase1 spec.md'],
                     capture_output=True).stdout
corrupted = raw.decode('utf-8')

# Also get the v1.1 spec for reference
raw1 = subprocess.run(['git', 'cat-file', '-p', 'HEAD~1:docs/phase1 spec.md'],
                      capture_output=True).stdout
v1 = raw1.decode('utf-8')

lines = corrupted.split('\n')

result_lines = []
for line in lines:
    stripped = line.strip()
    # Keep clearly ASCII lines
    if not stripped:
        result_lines.append(line.rstrip())
        continue

    # Calculate ASCII ratio
    ascii_count = sum(1 for c in stripped if ord(c) < 128)
    total = max(1, len(stripped))
    ratio = ascii_count / total

    # Keep lines that are mostly ASCII (English, code, punctuation, numbers)
    if ratio >= 0.30:
        result_lines.append(line.rstrip())
    elif any(kw in stripped for kw in ['#', '|', '---', '```', 'POST', 'HTTP',
                                         'S0-', 'S1-', 'api/', 'core/', 'services/',
                                         'type=', '→', '✓', '✗', '✅', '❌', 'Qdrant',
                                         'LLM', 'SLM', 'API', 'SQLite']):
        result_lines.append(line.rstrip())
    # For low-ASCII lines (mostly corrupted Chinese), skip them

result = '\n'.join(result_lines)

with open('F:/ai-knowledge-system/docs/phase1 spec.md', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Written {len(result)} chars, {len(result_lines)} lines")
print("First lines:")
for l in result.split('\n')[:15]:
    print(f"  {l[:100]}")

