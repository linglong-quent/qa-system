import pathlib
p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

# cid 到 config key 的映射
old = '                    sev = self.config.get(cid, {}).get("severity", "INFO")\n                    if sev == "BLOCKER":\n                        blocker_errors += errors\n                    if errors:'
new = '''                    cfg_key = cid.replace("_check", "")
                    sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))
                    if sev == "BLOCKER":
                        blocker_errors += errors
                    if errors:'''
assert old in t
t = t.replace(old, new, 1)

# 第二处
old2 = '                sev = self.config.get(cid, {}).get("severity", "INFO")\n                if sev == "BLOCKER":\n                    blocker_errors += errors\n                if errors:'
new2 = '''                cfg_key = cid.replace("_check", "")
                sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))
                if sev == "BLOCKER":
                    blocker_errors += errors
                if errors:'''
assert old2 in t
t = t.replace(old2, new2, 1)

p.write_text(t, encoding='utf-8')
print("fixed: severity lookup now tries both cid and cfg_key")
