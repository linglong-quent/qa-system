import pathlib
p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

# 修 line 381：用 blocker_errors 不是 total_errors
old = '            report["blocked"] = total_errors > 0 and not self.bootstrap'
new = '            report["blocked"] = blocker_errors > 0 and not self.bootstrap'
assert old in t
t = t.replace(old, new)

# 撤回 debug print
t = t.replace('''            print(f"DEBUG: blocker_errors={blocker_errors}, total_errors={total_errors}, bootstrap={self.bootstrap}")
            "blocked": blocker_errors > 0 and not self.bootstrap,''',
'''            "blocked": blocker_errors > 0 and not self.bootstrap,''')

p.write_text(t, encoding='utf-8')
print("fixed: quality_gates now also uses blocker_errors for blocked")
