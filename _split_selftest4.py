import pathlib

p = pathlib.Path("scripts/qa_self_test.py")
lines = p.read_text(encoding='utf-8').split('\n')

# main() 从 line 56 (index 55) 开始
# 找 section 3 (YAML syntax) 的行号
main_start = None
section3_start = None
for i, line in enumerate(lines):
    if line.startswith('def main()'):
        main_start = i
    if section3_start is None and main_start is not None and 'print("3.' in line:
        section3_start = i
        break

print(f"main starts at line {main_start+1}")
print(f"section 3 starts at line {section3_start+1}")

# 把 main_start 到 section3_start 之前的代码提取成函数
func_lines = lines[main_start:section3_start]
# 去掉 global 和 base/scripts_dir 赋值（函数参数化）
func_lines[0] = 'def _test_file_and_ast(base: str, scripts_dir: str):'
# 删除 global 行和 base/scripts_dir 行
new_func = []
for line in func_lines:
    if 'global passed, failed' in line:
        continue
    if 'base = _PROJECT_ROOT' in line:
        continue
    if 'scripts_dir = _SCRIPTS_DIR' in line:
        continue
    new_func.append(line)

# main() 重新开始
new_main = ['def main():  # noqa: STYLE-06',
            '    global passed, failed',
            '    base = _PROJECT_ROOT',
            '    scripts_dir = _SCRIPTS_DIR',
            '',
            '    _test_file_and_ast(base, scripts_dir)',
            '']

# 组装
result = lines[:main_start] + new_func + new_main + lines[section3_start:]
p.write_text('\n'.join(result), encoding='utf-8')
print("split done")
