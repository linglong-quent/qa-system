"""分析 BAN-9 文件性质，区分业务代码 vs 脚本"""
import json
import re
from collections import defaultdict

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban9 = [i for i in issues if i.startswith("[BAN-9]")]

by_file = defaultdict(list)
for issue in ban9:
    m = re.match(r'\[BAN-9\]\s+(.+?):(\d+)\s+(.+)', issue)
    if m:
        fpath = m.group(1)
        lineno = int(m.group(2))
        by_file[fpath].append(lineno)

# 分类
business_files = []  # 业务代码 - 必须改
script_files = []    # 脚本 - 可接受
factory_files = []   # 工厂/管理器 - 应排除

for fpath in by_file:
    fname = fpath.split('\\')[-1].split('/')[-1]
    
    # 工厂/连接管理器
    if 'db_conn' in fname or 'db_config' in fname:
        factory_files.append((fname, fpath, len(by_file[fpath])))
    # 建表/迁移/健康检查脚本
    elif any(k in fname for k in ['schema', 'migration', 'health', 'backup', 'monitor', 'evolution']):
        script_files.append((fname, fpath, len(by_file[fpath])))
    # 采集器/适配器
    elif any(k in fname for k in ['capture', 'adapter', 'realtime']):
        business_files.append((fname, fpath, len(by_file[fpath])))
    # API/业务逻辑
    else:
        business_files.append((fname, fpath, len(by_file[fpath])))

print(f"=== 工厂/管理器（应排除）=== {sum(x[2] for x in factory_files)}处")
for fname, fpath, cnt in factory_files:
    print(f"  {fname}: {cnt}处")

print(f"\n=== 运维/监控脚本（可接受）=== {sum(x[2] for x in script_files)}处")
for fname, fpath, cnt in script_files:
    print(f"  {fname}: {cnt}处")

print(f"\n=== 业务代码（建议改）=== {sum(x[2] for x in business_files)}处")
for fname, fpath, cnt in business_files:
    print(f"  {fname}: {cnt}处")
