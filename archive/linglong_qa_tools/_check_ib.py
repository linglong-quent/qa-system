"""找 import_boundary 的结果"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

ib = report['checkers']['import_boundary']
print(f"status: {ib.get('status', '?')}")
print(f"errors: {ib.get('errors', 0)}")
for key in ib:
    if key in ('status', 'errors'):
        continue
    val = ib[key]
    if isinstance(val, list) and len(val) > 0:
        print(f"\n{key} ({len(val)}项):")
        for item in val[:5]:
            print(f"  {str(item)[:120]}")
    elif isinstance(val, (str, int, float, bool)):
        print(f"{key}: {val}")
