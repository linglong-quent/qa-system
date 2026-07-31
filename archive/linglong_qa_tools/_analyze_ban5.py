"""分析 BAN-5 分布，找出核心业务参数 vs 函数内小数字"""
import json
import re
from collections import defaultdict, Counter

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban5 = [i for i in issues if i.startswith("[BAN-5]")]

print(f"BAN-5 总数: {len(ban5)}")

# 按文件/模块分组
by_domain = defaultdict(list)
for issue in ban5:
    m = re.match(r'\[BAN-5\]\s+(.+?):(\d+)\s+魔法数字\s+(.+?)\s+->', issue)
    if m:
        fpath = m.group(1)
        lineno = int(m.group(2))
        val = m.group(3)
        # 提取顶层目录/领域
        parts = fpath.replace('\\', '/').split('/')
        # 找 domain 后的第一个目录
        domain = "other"
        for i, p in enumerate(parts):
            if p == 'domain' and i + 1 < len(parts):
                domain = parts[i+1]
                break
            if p == 'ops':
                domain = 'ops'
                break
            if p == 'shared':
                domain = 'shared'
                break
        by_domain[domain].append((fpath, lineno, val))

print("\n按领域分布:")
for domain, items in sorted(by_domain.items(), key=lambda x: -len(x[1])):
    print(f"  {domain:20s} {len(items):>4} 个 ({len(items)/len(ban5)*100:.1f}%)")

# 按数值分布
val_counter = Counter()
for issue in ban5:
    m = re.match(r'\[BAN-5\]\s+(.+?):(\d+)\s+魔法数字\s+(.+?)\s+->', issue)
    if m:
        val_counter[m.group(3)] += 1

print(f"\nTop 20 高频数值:")
for val, cnt in val_counter.most_common(20):
    print(f"  {val:>10s}  {cnt:>4} 次")

# 看看 access 领域的具体情况
print(f"\naccess 领域文件分布:")
access_files = defaultdict(int)
for fpath, lineno, val in by_domain.get('access', []):
    fname = fpath.split('\\')[-1].split('/')[-1]
    access_files[fname] += 1

for fname, cnt in sorted(access_files.items(), key=lambda x: -x[1]):
    print(f"  {fname:40s} {cnt:>3} 个")
