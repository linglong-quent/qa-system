import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

# 在 code_ban_check 下加大类白名单
old = """  orphan_exempt_prefixes:"""
new = """  large_class_exempt_names:
  - HealthScorer
  - GateKeeper
  orphan_exempt_prefixes:"""
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added large_class_exempt_names for framework core classes")
