"""BAN-9 修复：裸 connect_db() → shared.db_conn.connect_db

只处理简单的、直接的 connect_db(db_path) 调用
复杂的（带很多参数的）后面再看
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

# 先列出所有有 sqlite3.connect 的文件，看看具体情况
files_with_sqlite = []

for root, dirs, files in os.walk(ROOT):
    if any(x in root.replace('\\', '/') for x in ['/.git', '__pycache__', '/.venv', '_probe', '/.ai', 'node_modules', 'tests']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        with open(fpath, 'r', encoding='utf-8') as fh:
            content = fh.read()
        if 'connect_db()(' in content and f != 'db_conn.py':
            count = content.count('connect_db(')
            rel = os.path.relpath(fpath, ROOT)
            files_with_sqlite.append((rel, count, fpath))

print(f"共 {len(files_with_sqlite)} 个文件有 connect_db()")
for rel, cnt, _ in sorted(files_with_sqlite, key=lambda x: -x[1]):
    print(f"  {rel}: {cnt} 处")

# 现在逐个修（只修简单的）
print("\n" + "=" * 60)
print("开始修复...")

fixed_files = 0
fixed_count = 0

for rel, cnt, fpath in files_with_sqlite:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经 import 了 shared.db_conn
    has_shared_import = 'from shared.db_conn' in content or 'import shared.db_conn' in content
    has_domain_db_import = 'from domain.data.api.db' in content
    
    # 计算相对路径，看用哪个import
    # 统一用 from shared.db_conn import connect_db
    if not has_shared_import and not has_domain_db_import:
        # 找插入位置
        lines = content.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i < 3 and (stripped.startswith('#!') or stripped.startswith('# -*-') or stripped.startswith('"""') or stripped.startswith("'''")):
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                insert_idx = i + 1
                continue
            if not stripped or stripped.startswith('#'):
                continue
            break
        
        # 插入 import
        lines.insert(insert_idx, "from shared.db_conn import connect_db\n")
        content = ''.join(lines)
    
    # 替换 connect_db(xxx) → connect_db(xxx)
    # 但要注意：sqlite3.connect 可能有不同的参数形式
    # 简单替换：connect_db()( → connect_db(
    # 但 connect_db 的签名是 (db_path, busy_timeout=...) 
    # 而 sqlite3.connect 的签名是 (database, timeout=...)
    # 所以需要更仔细的处理
    
    # 先统计一下各种形式
    new_content = content.replace('connect_db()(', 'connect_db(')
    new_count = content.count('connect_db(')
    
    if new_count > 0:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        fixed_files += 1
        fixed_count += new_count
        print(f"  ✓ {rel}: {new_count} 处")

print(f"\n总计: {fixed_files} 个文件, {fixed_count} 处")

# 语法验证
print("\n语法验证:")
errors = 0
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
            errors += 1
            rel = os.path.relpath(fpath, ROOT)
            print(f"  ✗ {rel}: line {e.lineno}: {e.msg}")

print(f"\n检查 {checked} 个文件，语法错误: {errors} 个")
