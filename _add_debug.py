import pathlib
p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

# 在 blocked 行前加调试
old = '"blocked": blocker_errors > 0 and not self.bootstrap,'
new = '''print(f"DEBUG: blocker_errors={blocker_errors}, total_errors={total_errors}, bootstrap={self.bootstrap}")
            "blocked": blocker_errors > 0 and not self.bootstrap,'''
assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added debug print")
