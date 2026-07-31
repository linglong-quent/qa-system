import json
import re
from collections import Counter

report_path = r'E:\WB\QA-System\.ai\logs\linglong_local\qa-report.json'
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

issues = report['checkers']['code_ban']['issues']

ban5 = [i for i in issues if 'BAN-5' in i]
ban10 = [i for i in issues if 'BAN-10' in i]
other = [i for i in issues if 'BAN-5' not in i and 'BAN-10' not in i]

print(f'code_ban 总问题数: {len(issues)}')
print(f'BAN-5 魔法数字: {len(ban5)}')
print(f'BAN-10 超大类: {len(ban10)}')
if other:
    print(f'其他: {len(other)}')
    for i in other[:10]:
        print(f'  {i}')

# 分析 BAN-5 的高频数字
magic_numbers = []
for issue in ban5:
    m = re.search(r'魔法数字 ([\d.eE+-]+)', issue)
    if m:
        magic_numbers.append(m.group(1))

counter = Counter(magic_numbers)
print(f'\nBAN-5 高频数字 TOP 20:')
for num, count in counter.most_common(20):
    print(f'  {num}: {count} 次')

# 按文件分布
file_counter = Counter()
for issue in ban5:
    m = re.search(r'\] (.+?):\d+', issue)
    if m:
        file_counter[m.group(1)] += 1

print(f'\nBAN-5 按文件 TOP 20:')
for f, count in file_counter.most_common(20):
    print(f'  {f}: {count} 个')

# BAN-10 详情
print(f'\nBAN-10 超大类详情:')
for i in ban10:
    print(f'  {i}')
