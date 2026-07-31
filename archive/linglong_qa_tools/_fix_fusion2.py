"""直接修复 fusion.py 的 fuse_configs 函数"""

path = r"E:\WB\linglong\domain\factor\engines\fusion.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_func = '''    # 读取 _core/config.py 的阈值 (通过 import)
    try:
        # 尝试从 _core/config.py 导入阈值（如果存在）
        try:
            from _core.config import (
                ARBITRATOR_ENABLED,
                AUTO_SYNC_ENABLED,
                COVERAGE_MIN_PCT,
                DD_TOLERANCE,
                MAX_CANDIDATE_POOL,
                RET_TOLERANCE,
            )

        merged["_py_thresholds"] = {
            "RET_TOLERANCE": RET_TOLERANCE,
            "DD_TOLERANCE": DD_TOLERANCE,
            "COVERAGE_MIN_PCT": COVERAGE_MIN_PCT,
            "MAX_CANDIDATE_POOL": MAX_CANDIDATE_POOL,
        }
        merged["_flags"] = {
            "AUTO_SYNC": AUTO_SYNC_ENABLED,
            "ARBITRATOR": ARBITRATOR_ENABLED,
        }
    except Exception:
        pass'''

new_func = '''    # 读取 _core/config.py 的阈值 (通过 import)
    try:
        from _core.config import (
            ARBITRATOR_ENABLED,
            AUTO_SYNC_ENABLED,
            COVERAGE_MIN_PCT,
            DD_TOLERANCE,
            MAX_CANDIDATE_POOL,
            RET_TOLERANCE,
        )
        merged["_py_thresholds"] = {
            "RET_TOLERANCE": RET_TOLERANCE,
            "DD_TOLERANCE": DD_TOLERANCE,
            "COVERAGE_MIN_PCT": COVERAGE_MIN_PCT,
            "MAX_CANDIDATE_POOL": MAX_CANDIDATE_POOL,
        }
        merged["_flags"] = {
            "AUTO_SYNC": AUTO_SYNC_ENABLED,
            "ARBITRATOR": ARBITRATOR_ENABLED,
        }
    except Exception:
        pass'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ fuse_configs 函数已修复")
else:
    print("✗ 未找到匹配的代码块")
    # 显示行 80-105
    lines = content.splitlines()
    for i in range(79, min(105, len(lines))):
        print(f"  {i+1}: {lines[i]}")

# 验证
import ast
with open(path, "r", encoding="utf-8") as f:
    source = f.read()
try:
    ast.parse(source)
    print("\n✓ 语法验证通过")
except SyntaxError as e:
    print(f"\n✗ 仍有语法错误: line {e.lineno}: {e.msg}")
