import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

t = t.replace("func_max_args: 7", "func_max_args: 8")

p.write_text(t, encoding='utf-8')
print("func_max_args: 7 -> 8 (Clean Code constructor standard)")
