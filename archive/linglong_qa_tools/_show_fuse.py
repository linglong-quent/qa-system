# -*- coding: utf-8 -*-
import os, sys, json, re

QA_SYSTEM_ROOT = r"E:\WB\QA-System"
os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = "linglong_local"
sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))

report_path = os.path.join(QA_SYSTEM_ROOT, r".ai\logs\linglong_local\qa-report.json")
with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

fuse = report["checkers"].get("fusedetect", {})
issues = fuse.get("issues", [])
print(f"fusedetect: errors={fuse.get('errors',0)}, issues={len(issues)}")

file_counts = {}
for issue in issues:
    m = re.match(r'\[FUSE-\d+\]\s+(\S+):(\d+)', issue)
    if m:
        fpath = m.group(1)
        file_counts[fpath] = file_counts.get(fpath, 0) + 1

print("\n按文件分布:")
for f, c in sorted(file_counts.items(), key=lambda x: -x[1]):
    print(f"  {f}: {c}")
