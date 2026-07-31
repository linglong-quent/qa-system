"""回退：git checkout 所有py文件到HEAD
然后用ast节点安全地批量修改
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import subprocess

ROOT = str(PROJECT_ROOT)

# 用 git 回退
result = subprocess.run(
    ["git", "checkout", "HEAD", "--", "."],
    cwd=ROOT,
    capture_output=True,
    text=True
)
print("git checkout:", result.returncode)
if result.stderr:
    print(result.stderr[-500:])

# 验证语法错误归零
import ast
errors = 0
for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                ast.parse(fh.read())
        except SyntaxError:
            errors += 1

print(f"\n回退后语法错误: {errors} 个")
if errors == 0:
    print("✓ 全部干净")
