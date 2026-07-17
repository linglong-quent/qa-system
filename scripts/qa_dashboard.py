#!/usr/bin/env python3
"""QA Dashboard — 从 qa-report.json 生成 HTML 看板"""
import json, os, sys
from datetime import datetime
from pathlib import Path

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)


def generate(report: dict, output_path: str = "") -> str:
    if not output_path:
        output_path = os.path.join(_PROJECT_ROOT, ".ai/logs/dashboard.html")

    # 质量分 = 100 - (errors * 5 + issues * 1)
    score = max(0, 100 - report.get("errors", 0) * 5 - report.get("total_issues", 0) * 1)
    ts = report.get("timestamp", datetime.now().isoformat())[:19]

    rows = ""
    for cid, data in sorted(report.get("checkers", {}).items()):
        if data.get("skipped"):
            rows += f"<tr><td>{cid}</td><td>⏭️</td><td>skipped</td><td>0</td><td class='m'></td></tr>\n"
            continue
        err = data.get("errors", 0)
        label = data.get("label", cid)
        status = "✅" if err == 0 else "❌"
        color = "#4ade80" if err == 0 else "#f87171"
        bar = "<div class='bar' style='width:" + str(max(5, 100 - err * 10)) + "%;background:" + color + "'></div>"
        rows += f"<tr><td>{label}</td><td>{status}</td><td>{err}</td><td>{len(data.get('issues',[]))}</td><td class='m'>{bar}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'><title>QA Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
body{{background:#0f172a;color:#e2e8f0;padding:40px}}
h1{{font-size:24px;margin-bottom:8px}}
.sub{{color:#64748b;margin-bottom:24px}}
.score{{font-size:64px;font-weight:bold}}
.good{{color:#4ade80}}.warn{{color:#fbbf24}}.bad{{color:#f87171}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:24px 0}}
.card{{background:#1e293b;padding:20px;border-radius:8px;text-align:center}}
.card .n{{font-size:32px;font-weight:bold}}.card .l{{font-size:12px;color:#64748b}}
table{{width:100%;border-collapse:collapse;margin-top:24px}}
th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid #1e293b;font-size:13px}}
th{{color:#64748b;font-weight:500}}
.bar{{height:6px;border-radius:3px;min-width:5px}}
.m{{width:120px}}
</style>
</head>
<body>
<h1>QA Dashboard</h1>
<p class='sub'>{ts} | {report.get('profile','full')} mode | {report.get('project_root','')}</p>

<div class='grid'>
  <div class='card'><div class='n {chr(103)+chr(111)+chr(111)+chr(100) if score >= 80 else "warn" if score >= 50 else "bad"}'>{score}</div><div class='l'>Quality Score</div></div>
  <div class='card'><div class='n {"good" if report.get("errors",0)==0 else "bad"}'>{report.get("errors",0)}</div><div class='l'>Errors</div></div>
  <div class='card'><div class='n'>{report.get("total_issues",0)}</div><div class='l'>Issues</div></div>
  <div class='card'><div class='n {"good" if not report.get("blocked",True) else "bad"}'>{chr(9989) if not report.get("blocked",True) else "DENY"}</div><div class='l'>Gate</div></div>
</div>

<table>
<tr><th>Checker</th><th></th><th>Errors</th><th>Issues</th><th></th></tr>
{rows}
</table>
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


if __name__ == "__main__":
    report_path = os.path.join(_PROJECT_ROOT, ".ai/logs/qa-report.json")
    if os.path.exists(report_path):
        report = json.load(open(report_path, encoding="utf-8"))
        path = generate(report)
        print(f"Dashboard: {path}")
    else:
        print("No report. Run qa_check.py health first")
