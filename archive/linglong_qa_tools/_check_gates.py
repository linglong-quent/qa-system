"""查看门禁详情"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

# 找 gate 信息
for key in report:
    if 'gate' in key.lower() or '门禁' in key:
        print(f"key: {key}")
        print(report[key])
        print()

# 看 governance
if 'governance' in report:
    print("=== governance ===")
    print(json.dumps(report['governance'], indent=2, ensure_ascii=False)[:1000])

# 看所有 checker 状态
print("\n=== checkers 状态 ===")
for name, data in report.get('checkers', {}).items():
    status = data.get('status', '')
    errors = data.get('errors', 0)
    print(f"  {name:30s} {status:10s} errors={errors}")
