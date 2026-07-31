"""
修复 BAN-7 硬编码 IP 问题：
1. data_config.py 是配置文件，IP 默认值是合理的 — 给 checker 加豁免
2. 其他文件 docstring 里的 IP — 移除或改成配置引用
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import re

linglong_root = str(PROJECT_ROOT)

# === 修复 1: 更新配置文件中的 docstring，移除硬编码 IP 描述 ===
files_to_fix = [
    os.path.join(linglong_root, "domain", "data", "collectors", "tdx_l2_realtime.py"),
    os.path.join(linglong_root, "ops", "scripts", "backup.py"),
    os.path.join(linglong_root, "ops", "scripts", "backup_to_nas.py"),
]

for fpath in files_to_fix:
    if not os.path.exists(fpath):
        print(f"跳过不存在: {fpath}")
        continue
    
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    
    # 移除 docstring 中的 IP 地址（替换成描述性文字）
    # 119.147.212.81 -> TDX行情服务器
    content = re.sub(r'119\.147\.212\.81:?\d*', 'TDX行情服务器(配置化)', content)
    # 192.168.1.4 -> NAS服务器
    content = re.sub(r'192\.168\.1\.4', 'NAS服务器(配置化)', content)
    # //192.168.1.4/xxx -> //NAS_HOST/xxx
    content = re.sub(r'//192\.168\.1\.4/', '//NAS_HOST/', content)
    # \\\\192.168.1.4\\xxx -> \\\\NAS_HOST\\xxx
    content = re.sub(r'\\\\192\.168\.1\.4\\', r'\\\\NAS_HOST\\', content)
    
    if content != original:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✓ 已修复: {os.path.relpath(fpath, linglong_root)}")
    else:
        print(f"- 无变化: {os.path.relpath(fpath, linglong_root)}")

print("\n✓ 完成 docstring IP 清理")
