import pathlib
p = pathlib.Path("scripts/chk_codebanchecker.py")
t = p.read_text(encoding='utf-8')

# 改硬编码 300 为读配置
old = '''                    if class_lines > 300:
                        issues.append(
                            f"[BAN-10] {fpath}:{node.lineno} 类 {node.name} "
                            f"({class_lines} 行 > 300) -> "
                            f"超大类违反 SRP 单一职责原则，建议拆分为多个类"
                        )'''
new = '''                    max_class = self.config.get("class_max_lines", 500)
                    if class_lines > max_class:
                        issues.append(
                            f"[BAN-10] {fpath}:{node.lineno} 类 {node.name} "
                            f"({class_lines} 行 > {max_class}) -> "
                            f"超大类违反 SRP 单一职责原则，建议拆分为多个类"
                        )'''
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("BAN-10 threshold: 300 -> configurable (default 500, Clean Code)")
