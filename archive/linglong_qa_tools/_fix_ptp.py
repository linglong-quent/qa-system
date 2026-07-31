"""修复 ptp_validator.py 的 f-string 语法错误"""

path = r"E:\WB\linglong\shared\ptp_validator.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 替换第226行（索引225）
old_line = lines[225]
new_line = '''    check_mark = "\u2705"
    cross_mark = "\u274c"
    status = f"{check_mark} 全部通过" if report.passed else f"{cross_mark} {len(report.violations)} 个违规"
    print(f"PTP 校验结果: {status}")
'''

# 替换 225-227 行（print语句）
# 先看一下上下文
print("原代码（行 223-230）:")
for i in range(222, min(230, len(lines))):
    print(f"  {i+1}: {lines[i].rstrip()}")

# 替换
old_block = """    print(
        f"PTP \\u6821\\u9a8c\\u7ed3\\u679c: {'\\u2705 \\u5168\\u90e8\\u901a\\u8fc7' if report.passed else '\\u274c %d \\u4e2a\\u8fdd\\u53cd' % len(report.violations)}")
    )
"""

# 直接用行号替换更可靠
new_lines = (
    lines[:224] +  # 到 print( 之前
    [
        '    check_mark = "\\u2705"\n',
        '    cross_mark = "\\u274c"\n',
        '    status = f"{check_mark} 全部通过" if report.passed else f"{cross_mark} {len(report.violations)} 个违规"\n',
        '    print(f"PTP 校验结果: {status}")\n',
    ] +
    lines[227:]  # 跳过原来的3行（print( + f-string + )）
)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("\n✓ 已修复")

# 验证语法
import ast
with open(path, "r", encoding="utf-8") as f:
    source = f.read()
try:
    ast.parse(source)
    print("✓ 语法验证通过")
except SyntaxError as e:
    print(f"✗ 仍有语法错误: line {e.lineno}: {e.msg}")
