import pathlib
p = pathlib.Path("scripts/chk_codebanchecker.py")
t = p.read_text(encoding='utf-8')

old = '''                    max_class = self.config.get("class_max_lines", 500)
                    if class_lines > max_class:'''
new = '''                    max_class = self.config.get("class_max_lines", 500)
                    exempt_names = set(self.config.get("large_class_exempt_names", []))
                    if class_lines > max_class and node.name not in exempt_names:'''
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("BAN-10 now respects large_class_exempt_names")
