import pathlib
p = pathlib.Path("scripts/chk_solid.py")
t = p.read_text(encoding='utf-8')

# 加 exempt 配置读取
old = '        self.allowed_concrete = set(cfg.get("allowed_concrete", []))'
new = '''        self.allowed_concrete = set(cfg.get("allowed_concrete", []))
        self.exempt_class_names = set(cfg.get("exempt_class_names", []))
        self.exempt_func_names = set(cfg.get("exempt_func_names", []))'''
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added exempt config reading to SOLID checker")
