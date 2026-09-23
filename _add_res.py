import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

# 排除 qlib 开源库
old = '''semantic_truth_check:
  enabled: true
  severity: BLOCKER
  scan_dirs:
  - src/
  - scripts/
  - domain/
  - D:/WB/TDX
  - D:/WB/NEWSFORGE
  - D:/WB/factor_forge'''

new = '''semantic_truth_check:
  enabled: true
  severity: BLOCKER
  scan_dirs:
  - src/
  - scripts/
  - domain/
  - D:/WB/TDX
  - D:/WB/NEWSFORGE
  - D:/WB/factor_forge
  exclude_patterns:
  - "**/open_source_systems/**"
  - "**/.t18_*"'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("排除 qlib 开源库")
