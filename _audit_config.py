import pathlib, re

t = pathlib.Path(".ai/config/review-rules.yaml").read_text(encoding='utf-8')

# 找所有放宽/开发阶段的配置
lines = t.split('\n')
print("=== 开发阶段放宽项（需生产级收紧）===\n")
for i, line in enumerate(lines, 1):
    if any(kw in line.lower() for kw in ['dev', '开发', 'warn', '宽松', 'relax', 'grace', 'max_lines: 200', 'max_args: 8', 'max_methods: 25', 'drift_grace']):
        print(f"  L{i}: {line.strip()[:80]}")
