import pathlib

p = pathlib.Path("scripts/chk_governance.py")
t = p.read_text(encoding='utf-8')

old = '''        if pkg_dirs_without_init > 0 and has_src:
            issues.append(f"[PY-09] {pkg_dirs_without_init} 个含 .py 的目录缺少 __init__.py")
            errors += 1'''

new = '''        if pkg_dirs_without_init > 0 and has_src:
            issues.append(f"[PY-09] {pkg_dirs_without_init} 个含 .py 的目录缺少 __init__.py")
            errors += 1

        return errors'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added return errors")
