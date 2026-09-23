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

# 提取 RULES（缩进从 8 空格降到 0）
rules_lines = lines[rules_start:rules_end+1]
new_rules = []
for line in rules_lines:
    if line.startswith('        '):
        new_rules.append(line[8:])
    else:
        new_rules.append(line)

# 在 import 之后、class 之前插入 RULES
class_start = None
for i, line in enumerate(lines):
    if line.startswith('class HealthScorer:'):
        class_start = i
        break

print(f"class at {class_start+1}")

# 组装
before_class = lines[:class_start]
after_class = lines[class_start:rules_start] + lines[rules_end+1:]

result = before_class + new_rules + [''] + after_class
p.write_text('\n'.join(result), encoding='utf-8')
print("moved RULES to module level")
