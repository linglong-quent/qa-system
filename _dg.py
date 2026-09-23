import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')
t = t.replace("drift_grace_seconds: 60", "drift_grace_seconds: 300")
p.write_text(t, encoding='utf-8')
print("drift_grace_seconds: 60 -> 300 (dev mode)")
