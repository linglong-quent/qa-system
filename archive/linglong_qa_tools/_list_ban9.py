"""列出所有 BAN-9 裸DB连接的具体位置"""
import json
import re
from collections import defaultdict

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban9 = [i for i in issues if i.startswith("[BAN-9]")]

print(f"BAN-9 总数: {len(ban9)}")

by_file = defaultdict(list)
for issue in ban9:
    m = re.match(r'\[BAN-9\]\s+(.+?):(\d+)\s+(.+)', issue)
    if m:
        fpath = m.group(1)
        lineno = int(m.group(2))
        content = m.group(3)
        by_file[fpath].append((lineno, content))

for fpath, items in sorted(by_file.items()):
    fname = fpath.split('\\')[-1].split('/')[-1]
    print(f"\n{fname}  ({len(items)}处)")
    for lineno, content in items[:5]:
        print(f"  L{lineno}: {content[:80]}")
    if len(items) > 5:
        print(f"  ... 还有 {len(items)-5} 处")
