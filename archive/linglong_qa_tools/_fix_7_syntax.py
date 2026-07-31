"""修复7个语法错误 + BOM问题
逐个处理，确保语法正确
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

ROOT = str(PROJECT_ROOT)

# ============================================================
# 1. data/build_sector_map.py - 括号没闭合 + 残留logger行
# ============================================================
print("1. 修复 build_sector_map.py")
fpath = os.path.join(ROOT, "data", "build_sector_map.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# 把残留的 logger.debug 行删掉，恢复正确结构
# 原始应该是 rows.append(( ... )) 然后 except
old = """                    rows.append((
                        code,
                        str(item.get('BlockCode', '')),
                        str(item.get('BlockName', '')),
                        str(item.get('BlockType', '')),
                        int(item.get('GPNume', 0))
            logger.debug("except Exception: %s", e)
        except Exception as e:
            pass  # 跳过出错"""

new = """                    rows.append((
                        code,
                        str(item.get('BlockCode', '')),
                        str(item.get('BlockName', '')),
                        str(item.get('BlockType', '')),
                        int(item.get('GPNume', 0))
                    ))
        except Exception:
            pass  # 跳过出错"""

if old in content:
    content = content.replace(old, new)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓")
else:
    print("  ✗ 未找到匹配内容")

# ============================================================
# 2. data/monitor_l2_activity.py - return括号没闭合 + 残留logger
# ============================================================
print("2. 修复 monitor_l2_activity.py")
fpath = os.path.join(ROOT, "data", "monitor_l2_activity.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

old = """            return (code, int(str(l2)) if str(l2).isdigit() else 0,
                    int(str(tic)) if str(tic).isdigit() else 0,
        logger.debug("except Exception: %s", e)
    except Exception:
        pass"""

new = """            return (code, int(str(l2)) if str(l2).isdigit() else 0,
                    int(str(tic)) if str(tic).isdigit() else 0,
                    str(zaf), str(hsl), str(zsz))
    except Exception:
        pass"""

if old in content:
    content = content.replace(old, new)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓")
else:
    print("  ✗ 未找到匹配内容")

# ============================================================
# 3. data/scan_l2_depth_coverage.py - try块被搞坏了
# ============================================================
print("3. 修复 scan_l2_depth_coverage.py")
fpath = os.path.join(ROOT, "data", "scan_l2_depth_coverage.py")
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

old = """                    try:
                        if float(str(v)) > 0 as e:
                        logger.debug("except Exception: %s", e)
                    except (ValueError, TypeError):
                        pass"""

new = """                    try:
                        if float(str(v)) > 0:
                            cnt += 1
                    except (ValueError, TypeError):
                        pass"""

if old in content:
    content = content.replace(old, new)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓")
else:
    print("  ✗ 未找到匹配内容")

# ============================================================
# 4. adversarial_review_l2.py - BOM问题 + 行顺序错了
# ============================================================
print("4. 修复 adversarial_review_l2.py (BOM)")
fpath = os.path.join(ROOT, "domain", "cognition", "engines", "adversarial_review_l2.py")
with open(fpath, 'rb') as f:
    data = f.read()

if data.startswith(b'\xef\xbb\xbf'):
    data = data[3:]
    with open(fpath, 'wb') as f:
        f.write(data)
    print("  ✓ BOM 已移除")
else:
    # BOM可能在第6行位置（因为前面有5行注释）
    # 直接读文本看看
    with open(fpath, 'r', encoding='utf-8') as f:
        text = f.read()
    if '\ufeff' in text:
        text = text.replace('\ufeff', '')
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(text)
        print("  ✓ 内联BOM已移除")
    else:
        print("  无BOM")

# ============================================================
# 5. domain/factor/engines/fusion.py - 缩进问题
# ============================================================
print("5. 修复 fusion.py (缩进)")
fpath = os.path.join(ROOT, "domain", "factor", "engines", "fusion.py")
with open(fpath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找有问题的那段：try: 后面直接是注释掉的config_module
# 第81-89行结构有问题
# 正确结构应该是：try: from ... import ... except: ...
# 但现在 try: 后面是注释 + 一堆变量，没有import语句

# 读更多上下文看看
for i in range(75, 110):
    if i < len(lines):
        print(f"  {i+1}: {lines[i].rstrip()}")
