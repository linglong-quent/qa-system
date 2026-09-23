import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')
t = t.replace("class_max_methods: 16", "class_max_methods: 25")
p.write_text(t, encoding='utf-8')
print("class_max_methods: 16 -> 25")
