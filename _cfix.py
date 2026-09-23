import pathlib

p = pathlib.Path("scripts/chk_container.py")
t = p.read_text(encoding='utf-8')

# 只检查 linglong-* 容器，其他跳过
old = '''        for r in rows:
            name = r.get("Names", "")
            status = r.get("Status", "")'''

new = '''        for r in rows:
            name = r.get("Names", "")
            # 只检查 linglong-* 项目容器，其他本地容器（dify/zeos/grafana）跳过
            if not name.startswith("linglong-"):
                continue
            status = r.get("Status", "")'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("container check: only linglong-* containers")
