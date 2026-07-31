"""分析 BAN-14 孤儿模块 — 看看检测逻辑"""

# 读 BAN-14 的检测代码
fpath = r"E:\WB\qa-system\scripts\chk_codebanchecker.py"

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# 找 _check_orphan_asset 函数
import re
m = re.search(r'def _check_orphan_asset\(self.*?(?=\n    def |\n    # ───)', content, re.DOTALL)
if m:
    print("=== _check_orphan_asset ===")
    print(m.group(0)[:2000])
else:
    print("没找到函数，搜索 orphan")
    for i, line in enumerate(content.split('\n'), 1):
        if 'orphan' in line.lower():
            print(f"  L{i}: {line[:80]}")
