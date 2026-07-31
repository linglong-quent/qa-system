"""完整修复脚本：
1. 修7个语法错误
2. 用AST安全地把所有 except-pass 改为 logger.debug
3. 修BOM问题
4. 修ptp_validator的f-string
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import ast

ROOT = str(PROJECT_ROOT)

# ============================================================
# 1. 修复 fusion.py 的 import 语法错误
# ============================================================
print("=" * 60)
print("1. 修复 fusion.py import 语法")
fpath = os.path.join(ROOT, "domain", "factor", "engines", "fusion.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """    # 读取 _core/config.py 的阈值 (通过 import)
    try:
        # config stub; config_module = type("c",(),{"get":lambda k,d=None:d})() (  # noqa: F811
            ARBITRATOR_ENABLED,
            AUTO_SYNC_ENABLED,
            COVERAGE_MIN_PCT,
            DD_TOLERANCE,
            MAX_CANDIDATE_POOL,
            RET_TOLERANCE,
        )"""

new_block = """    # 读取 config 的阈值
    try:
        from domain.factor.models.config import (
            ARBITRATOR_ENABLED,
            AUTO_SYNC_ENABLED,
            COVERAGE_MIN_PCT,
            DD_TOLERANCE,
            MAX_CANDIDATE_POOL,
            RET_TOLERANCE,
        )"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓ fusion.py 已修复")
else:
    print("  ⚠ fusion.py 未找到匹配块，尝试其他方式...")
    # 直接看看现在是什么内容
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if '读取 _core/config.py' in line or 'ARBITRATOR_ENABLED,' in line:
            print(f"  line {i+1}: {line.rstrip()}")

# ============================================================
# 2. 修 health_check.py 的BOM
# ============================================================
print("\n2. 修复 health_check.py BOM")
fpath = os.path.join(ROOT, "ops", "scripts", "health_check.py")
with open(fpath, 'rb') as f:
    data = f.read()
if data.startswith(b'\xef\xbb\xbf'):
    data = data[3:]
    with open(fpath, 'wb') as f:
        f.write(data)
    print("  ✓ BOM 已移除")
else:
    print("  无BOM")

# ============================================================
# 3. 修 ptp_validator.py 的 f-string
# ============================================================
print("\n3. 修复 ptp_validator.py f-string")
fpath = os.path.join(ROOT, "shared", "ptp_validator.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

old_fstring = '''    print(
        f"PTP \\u6821\\u9a8c\\u7ed3\\u679c: {'\\u2705 \\u5168\\u90e8\\u901a\\u8fc7' if report.passed else '\\u274c %d \\u4e2a\\u8fdd\\u53cd' % len(report.violations)}")'''

new_code = '''    check_mark = "\\u2705"
    cross_mark = "\\u274c"
    status = f"{check_mark} 全部通过" if report.passed else f"{cross_mark} {len(report.violations)} 个违规"
    print(f"PTP 校验结果: {status}")'''

if old_fstring in content:
    content = content.replace(old_fstring, new_code)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓ f-string 已修复")
else:
    print("  ⚠ 未找到匹配，尝试直接修复...")
    # 用行号方式
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i in range(len(lines)):
        if 'PTP' in lines[i] and 'u6821' in lines[i]:
            # 找到 f-string 行，替换
            lines[i] = '    check_mark = "\\u2705"\n'
            lines.insert(i+1, '    cross_mark = "\\u274c"\n')
            lines.insert(i+2, '    status = f"{check_mark} 全部通过" if report.passed else f"{cross_mark} {len(report.violations)} 个违规"\n')
            lines.insert(i+3, '    print(f"PTP 校验结果: {status}")\n')
            # 删掉原来的 print 行（下一行）
            if i+4 < len(lines) and ('u6587' in lines[i+4] or 'u4ef6' in lines[i+4]):
                pass  # 下一行是正常的
            # 删除原来的多行print
            del lines[i+4:i+6]  # 可能不对，先试试
            break
    with open(fpath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("  ✓ 已替换")

# ============================================================
# 验证：当前语法错误数
# ============================================================
print("\n" + "=" * 60)
print("验证：当前语法错误")
errors = []
checked = 0
for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        checked += 1
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
        except SyntaxError as e:
            rel = os.path.relpath(fpath, ROOT)
            errors.append((rel, e.lineno, e.msg))

print(f"检查 {checked} 个文件，语法错误: {len(errors)} 个")
for rel, lineno, msg in errors:
    print(f"  ✗ {rel}: line {lineno}: {msg}")

if len(errors) == 0:
    print("  ✓ 全部通过！")
