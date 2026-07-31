import json
import re
from collections import defaultdict

report_path = r'E:\WB\QA-System\.ai\logs\linglong_local\qa-report.json'
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

issues = report['checkers']['codestyle']['issues']

# 按目录统计
dir_stats = defaultdict(lambda: {'total': 0, 'STYLE-02': 0, 'STYLE-06': 0, 'STYLE-05': 0, 'STYLE-03': 0})

for issue in issues:
    m = re.search(r'\] ([^:]+):', issue)
    if m:
        fpath = m.group(1)
        top_dir = fpath.split('\\')[0] if '\\' in fpath else fpath.split('/')[0]
        dir_stats[top_dir]['total'] += 1
        for st in ['STYLE-02', 'STYLE-03', 'STYLE-05', 'STYLE-06']:
            if st in issue:
                dir_stats[top_dir][st] += 1

print('按顶层目录统计:')
for d in sorted(dir_stats.keys()):
    s = dir_stats[d]
    print(f'  {d}: 总计 {s["total"]} (02={s["STYLE-02"]}, 03={s["STYLE-03"]}, 05={s["STYLE-05"]}, 06={s["STYLE-06"]})')

# 统计 scripts/qa_tools/ 下的问题
qa_tool_issues = [i for i in issues if 'qa_tools' in i]
print(f'\nscripts/qa_tools/ 下的问题: {len(qa_tool_issues)}')

# 统计 scripts/ 下非 qa_tools 的问题
script_issues = [i for i in issues if i.startswith('] scripts\\') and 'qa_tools' not in i]
print(f'scripts/ 下非 qa_tools 的问题: {len(script_issues)}')
for i in script_issues[:20]:
    print(f'  {i}')
