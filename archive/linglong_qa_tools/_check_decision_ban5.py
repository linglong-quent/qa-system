"""分析 decision 领域 BAN-5 的具体文件"""
import json
import re
from collections import defaultdict

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban5 = [i for i in issues if i.startswith("[BAN-5]")]

# 只看 decision 领域
decision_issues = []
for issue in ban5:
    m = re.match(r'\[BAN-5\]\s+(.+?):(\d+)\s+魔法数字\s+(.+?)\s+->', issue)
    if m and 'decision' in m.group(1):
        decision_issues.append((m.group(1), int(m.group(2)), m.group(3)))

print(f"decision 领域 BAN-5: {len(decision_issues)} 个")

by_file = defaultdict(list)
for fpath, lineno, val in decision_issues:
    fname = fpath.split('\\')[-1].split('/')[-1]
    by_file[fname].append((lineno, val))

for fname, items in sorted(by_file.items(), key=lambda x: -len(x[1])):
    print(f"\n{fname} ({len(items)}个):")
    for lineno, val in sorted(items)[:10]:
        print(f"  L{lineno}: {val}")
    if len(items) > 10:
        print(f"  ... 还有 {len(items)-10} 个")
