import pathlib

p = pathlib.Path("scripts/chk_healthscorer.py")
lines = p.read_text(encoding='utf-8').split('\n')

# 找 RULES 开始和结束
rules_start = None
rules_end = None
for i, line in enumerate(lines):
    if line.strip() == 'RULES = {':
        rules_start = i
    if rules_start and line.strip() == '}' and i > rules_start + 10:
        rules_end = i
        break

print(f"RULES: {rules_start+1} - {rules_end+1}")

# 提取 RULES 成模块级常量（缩进 0）
rules_lines = lines[rules_start:rules_end+1]
new_rules = []
for line in rules_lines:
    if line.startswith('        '):
        new_rules.append(line[8:])
    else:
        new_rules.append(line)

# 在文件开头加 RULES
# 找类定义之前的位置
class_start = None
for i, line in enumerate(lines):
    if line.startswith('class HealthScorer:'):
        class_start = i
        break

print(f"class at line {class_start+1}")

# 把 RULES 移到 class 之前
result = lines[:class_start] + new_rules + [''] + lines[class_start:]

# 删除原位置的 RULES
result2 = []
skip = False
for line in result:
    if line.strip() == 'RULES = {':
        skip = True
    if skip:
        if line.strip() == '}':
            skip = False
        continue
    result2.append(line)

p.write_text('\n'.join(result2), encoding='utf-8')
print("moved RULES to module level")
