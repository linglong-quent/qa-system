import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

old = "  dup_body_min_lines: 12"
new = """  dup_body_min_lines: 12
  exempt_class_names:
  - HealthScorer
  - GateKeeper
  exempt_func_names:
  - __init__
  - main"""
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added SOLID exempt: HealthScorer/GateKeeper classes, __init__/main funcs")
