# -*- coding: utf-8 -*-
import os, sys, json, re

QA_SYSTEM_ROOT = r"E:\WB\QA-System"
os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = "linglong_local"
sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))

report_path = os.path.join(QA_SYSTEM_ROOT, r".ai\logs\linglong_local\qa-report.json")
with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

checkers = report.get("checkers", {})

new_checkers = ["lookahead", "inplace", "secret", "fusedetect", "securityplus"]

for cid in new_checkers:
    if cid in checkers:
        data = checkers[cid]
        issues = data.get("issues", [])
        print(f"\n=== {cid} ({len(issues)} issues) ===")
        if len(issues) <= 10:
            for i in issues:
                print(f"  {i}")
        else:
            # 统计按文件/模式分布
            file_counts = {}
            pattern_counts = {}
            for issue in issues:
                m = re.match(r'\[([^\]]+)\]\s+(\S+):(\d+)\s+(.*)', issue)
                if m:
                    fpath = m.group(2)
                    file_counts[fpath] = file_counts.get(fpath, 0) + 1
            print("  Top files:")
            for f, c in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
                print(f"    {f}: {c}")
            print(f"  ... 前10个文件，共 {len(file_counts)} 个文件")
            print("\n  前5条样例:")
            for i in issues[:5]:
                print(f"    {i}")
