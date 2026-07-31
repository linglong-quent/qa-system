"""找 Gate3 越域 import 的所有违规"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

# 找 import_boundary 的结果
if 'import_boundary_check' in report['checkers']:
    ib = report['checkers']['import_boundary_check']
    print(f"import_boundary status: {ib.get('status', '?')}")
    print(f"errors: {ib.get('errors', 0)}")
    if 'issues' in ib:
        for issue in ib['issues']:
            print(f"  {issue[:120]}")
    elif 'details' in ib:
        for d in ib['details']:
            print(f"  {str(d)[:120]}")
    else:
        print(f"keys: {list(ib.keys())}")
else:
    print("没有 import_boundary_check")
    # 看看有哪些 checker
    print(f"checkers: {list(report['checkers'].keys())}")
