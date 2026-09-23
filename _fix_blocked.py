import pathlib
p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

# 加 blocker_errors 跟踪
old = "        total_errors = 0\n        checker_results = {}"
new = "        total_errors = 0\n        blocker_errors = 0\n        checker_results = {}"
assert old in t
t = t.replace(old, new)

# 在两处 total_errors += errors 后加 blocker 跟踪
old2 = "                    total_errors += errors\n                    if errors:"
new2 = "                    total_errors += errors\n                    sev = self.config.get(cid, {}).get(\"severity\", \"INFO\")\n                    if sev == \"BLOCKER\":\n                        blocker_errors += errors\n                    if errors:"
assert old2 in t
t = t.replace(old2, new2, 1)  # 只替换第一处

old3 = "                total_errors += errors\n                if errors:"
new3 = "                total_errors += errors\n                sev = self.config.get(cid, {}).get(\"severity\", \"INFO\")\n                if sev == \"BLOCKER\":\n                    blocker_errors += errors\n                if errors:"
assert old3 in t
t = t.replace(old3, new3, 1)  # 只替换第二处

# 改 blocked 逻辑
old4 = '"blocked": total_errors > 0 and not self.bootstrap,'
new4 = '"blocked": blocker_errors > 0 and not self.bootstrap,'
assert old4 in t
t = t.replace(old4, new4)

p.write_text(t, encoding='utf-8')
print("blocked now only counts BLOCKER-severity checker errors")
