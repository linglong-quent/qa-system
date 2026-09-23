import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

# 加三仓到 scan_dirs
# 找 semantic_truth_check 的 scan_dirs
old = '''semantic_truth_check:
  enabled: true
  severity: BLOCKER
  scan_dirs:
  - src/
  - scripts/
  - domain/'''

new = '''semantic_truth_check:
  enabled: true
  severity: BLOCKER
  scan_dirs:
  - src/
  - scripts/
  - domain/
  - D:/WB/TDX
  - D:/WB/NEWSFORGE
  - D:/WB/factor_forge'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added 3 repos to semantic_truth_check scan_dirs")
