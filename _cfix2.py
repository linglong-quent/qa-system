import pathlib

p = pathlib.Path("scripts/chk_container.py")
t = p.read_text(encoding='utf-8')

old = '''            # 只检查 linglong-* 项目容器，其他本地容器（dify/zeos/grafana）跳过
            if not name.startswith("linglong-"):
                continue'''

new = '''            # 只检查量化项目相关容器（TDX/NEWSFORGE/FACTOR_FORGE/QA-SYSTEM/LINGLONG）
            _keep_prefixes = ("linglong-", "grafana", "tdx", "newsforge", "factor-forge", "qa-")
            if not name.startswith(_keep_prefixes):
                continue'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("container check: keep linglong/grafana/tdx/newsforge/factor-forge/qa-*")
