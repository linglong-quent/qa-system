import pathlib

p = pathlib.Path("scripts/chk_governance.py")
t = p.read_text(encoding='utf-8')

# 在 _check_cleanup_and_encoding 方法开头加 has_src 计算
old = '''    def _check_cleanup_and_encoding(self, issues: list) -> int:
        """Sections 4-6: pycache + encoding + __init__"""
        errors = 0'''

new = '''    def _check_cleanup_and_encoding(self, issues: list) -> int:
        """Sections 4-6: pycache + encoding + __init__"""
        errors = 0
        has_src = os.path.isdir(os.path.join(self.project_root, "src"))'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("fixed has_src in _check_cleanup_and_encoding")
