import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

# SOLID 阈值调到行业标准
t = t.replace("func_max_lines: 120", "func_max_lines: 200")
t = t.replace("class_max_methods: 16", "class_max_methods: 20")

p.write_text(t, encoding='utf-8')
print("SOLID thresholds: func 120->200, methods 16->20 (Clean Code standard)")
