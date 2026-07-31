"""分类查看QA检查结果，排除deadcode噪声"""
import json

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

print("=" * 60)
print("QA 检查结果分类汇总（排除deadcode噪声）")
print("=" * 60)

for cid, cdata in report["checkers"].items():
    if cid == "deadcode_check":
        continue
    if cdata.get("skipped"):
        continue
    err = cdata.get("errors", 0)
    if err > 0:
        print(f"\n❌ {cdata.get('label', cid)} ({err}个错误)")
        issues = cdata.get("issues", [])
        for i in issues[:10]:
            print(f"   - {i[:100]}")
        if len(issues) > 10:
            print(f"   ... 还有 {len(issues)-10} 个")

print(f"\n---")
print(f"总计: {report['errors']} 个错误（其中 deadcode {report['checkers'].get('deadcode_check', {}).get('errors', 0)} 个）")
print(f"非deadcode错误: {report['errors'] - report['checkers'].get('deadcode_check', {}).get('errors', 0)} 个")
