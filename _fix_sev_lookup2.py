import pathlib
p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

# 修正：cid -> config key 是加 _check，不是去
old = '''                    cfg_key = cid.replace("_check", "")
                    sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))'''
new = '''                    cfg_key = cid if cid.endswith("_check") else cid + "_check"
                    sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))'''
assert old in t
t = t.replace(old, new, 1)

old2 = '''                cfg_key = cid.replace("_check", "")
                sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))'''
new2 = '''                cfg_key = cid if cid.endswith("_check") else cid + "_check"
                sev = self.config.get(cid, {}).get("severity", self.config.get(cfg_key, {}).get("severity", "INFO"))'''
assert old2 in t
t = t.replace(old2, new2, 1)

p.write_text(t, encoding='utf-8')
print("fixed: severity lookup now adds _check suffix to cid")
