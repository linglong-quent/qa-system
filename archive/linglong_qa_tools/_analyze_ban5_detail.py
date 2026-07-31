import json
import re
from collections import Counter

report_path = r'E:\WB\QA-System\.ai\logs\linglong_local\qa-report.json'
with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

issues = report['checkers']['code_ban']['issues']
ban5 = [i for i in issues if 'BAN-5' in i]

# 获取所有唯一数字
magic_numbers = []
for issue in ban5:
    m = re.search(r'魔法数字 ([\d.eE+-]+)', issue)
    if m:
        magic_numbers.append(m.group(1))

counter = Counter(magic_numbers)
unique_nums = sorted(counter.keys(), key=lambda x: float(x))

print(f'唯一魔法数字数量: {len(unique_nums)}')
print('\n所有唯一数字（从小到大）:')
for num in unique_nums:
    count = counter[num]
    print(f'  {num}: {count} 次')

# 读取当前白名单
import yaml
config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找 magic_whitelist
magic_whitelist = config.get('magic_whitelist', [])
print(f'\n当前白名单数量: {len(magic_whitelist)}')
print(f'当前白名单: {sorted(magic_whitelist)}')

# 计算新增后能减少多少
not_in_whitelist = [n for n in unique_nums if float(n) not in magic_whitelist]
print(f'\n不在白名单中的数字: {len(not_in_whitelist)}')
for num in not_in_whitelist:
    count = counter[num]
    print(f'  {num}: {count} 次')
