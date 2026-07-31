# -*- coding: utf-8 -*-
import os, sys, json, re

QA_SYSTEM_ROOT = r"E:\WB\QA-System"
os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = "linglong_local"
sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))

report_path = os.path.join(QA_SYSTEM_ROOT, r".ai\logs\linglong_local\qa-report.json")
with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["codestyle"]["issues"]
style03 = [i for i in issues if "[STYLE-03]" in i]

print(f"STYLE-03 总计: {len(style03)}")

# 分类统计
cats = {"func": 0, "class": 0, "const": 0, "var": 0, "other": 0}
func_names = []
class_names = []
for issue in style03:
    if "函数" in issue and "snake_case" in issue:
        cats["func"] += 1
        m = re.search(r'(\w+)\s+函数', issue)
        if m:
            func_names.append(m.group(1))
    elif "类" in issue and "PascalCase" in issue:
        cats["class"] += 1
        m = re.search(r'(\w+)\s+类', issue)
        if m:
            class_names.append(m.group(1))
    elif "常量" in issue:
        cats["const"] += 1
    else:
        cats["other"] += 1

print("\n分类:")
for k, v in cats.items():
    print(f"  {k}: {v}")

if func_names:
    print(f"\n函数命名违规 (前30个): {sorted(set(func_names))[:30]}")
if class_names:
    print(f"\n类命名违规 (前30个): {sorted(set(class_names))[:30]}")

# 按文件统计
file_counts = {}
for issue in style03:
    m = re.match(r'\[STYLE-\d+\]\s+(\S+):(\d+)', issue)
    if m:
        fpath = m.group(1)
        file_counts[fpath] = file_counts.get(fpath, 0) + 1

print("\n按文件分布 (Top 15):")
for f, c in sorted(file_counts.items(), key=lambda x: -x[1])[:15]:
    print(f"  {f}: {c}")
