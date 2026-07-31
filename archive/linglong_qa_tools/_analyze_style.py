import json
import re

report_path = r'E:\WB\QA-System\.ai\logs\linglong_local\qa-report.json'
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

issues = report['checkers']['codestyle']['issues']
style03 = [i for i in issues if 'STYLE-03' in i]
style02 = [i for i in issues if 'STYLE-02' in i]
style05 = [i for i in issues if 'STYLE-05' in i]
style06 = [i for i in issues if 'STYLE-06' in i]
style04 = [i for i in issues if 'STYLE-04' in i]
style01 = [i for i in issues if 'STYLE-01' in i]

print(f'总问题数: {len(issues)}')
print(f'STYLE-01 文件名: {len(style01)}')
print(f'STYLE-02 行长度: {len(style02)}')
print(f'STYLE-03 命名: {len(style03)}')
print(f'STYLE-04 日志: {len(style04)}')
print(f'STYLE-05 文件行数: {len(style05)}')
print(f'STYLE-06 函数行数: {len(style06)}')

dunder_count = 0
non_dunder = []
for issue in style03:
    m = re.search(r"函数名 '(__\w+__)'", issue)
    if m:
        dunder_count += 1
    else:
        non_dunder.append(issue)

print(f'\nSTYLE-03 详细:')
print(f'  dunder 方法误报: {dunder_count}')
print(f'  真正命名问题: {len(non_dunder)}')
if non_dunder[:20]:
    print('  前 20 个真实问题:')
    for i in non_dunder[:20]:
        print(f'    {i}')
