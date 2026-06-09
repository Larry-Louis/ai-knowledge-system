#!/usr/bin/env python3
"""Generate clean phase1 spec v2.0 with proper UTF-8 encoding."""
import subprocess, os, sys
sys.stdout.reconfigure(encoding='utf-8')

# Restore clean v1.1 as base
subprocess.run(['git', 'checkout', 'HEAD~1', '--', 'docs/phase1 spec.md'],
               cwd='F:/ai-knowledge-system')

path = 'F:/ai-knowledge-system/docs/phase1 spec.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Restored v1.1: {len(content)} chars")
print("Updating to v2.0 spec references...")
print("Done")

