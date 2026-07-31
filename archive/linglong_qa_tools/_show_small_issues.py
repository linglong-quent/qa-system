# -*- coding: utf-8 -*-
import os, sys, json

QA_SYSTEM_ROOT = r"E:\WB\QA-System"
os.environ["QA_SYSTEM_ROOT"] = QA_SYSTEM_ROOT
os.environ["QA_PROJECT_NAME"] = "linglong_local"
sys.path.insert(0, os.path.join(QA_SYSTEM_ROOT, "scripts"))

report_path = os.path.join(QA_SYSTEM_ROOT, r".ai\logs\linglong_local\qa-report.json")
with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

print("=== securityplus (4 issues) ===")
for i in report["checkers"].get("securityplus", {}).get("issues", []):
    print(f"  {i}")

print("\n=== fusedetect (4 issues) ===")
for i in report["checkers"].get("fusedetect", {}).get("issues", []):
    print(f"  {i}")

print("\n=== governance (5 issues) ===")
for i in report["checkers"].get("governance", {}).get("issues", []):
    print(f"  {i}")

print("\n=== claude_validation (1 issue) ===")
for i in report["checkers"].get("claude_validation", {}).get("issues", []):
    print(f"  {i}")
