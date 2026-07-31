"""填充 data_config.py 配置"""
import os

config_path = r"E:\WB\linglong\domain\data\data_config.py"

content = '''"""数据层配置 — 所有业务参数集中管理

环境变量覆盖优先级: 环境变量 > 配置默认值
"""
import os

# === TDX 通达信配置 ===
TDX = {
    "l2_host": os.environ.get("TDX_L2_HOST", "119.147.212.81"),
    "l2_port": int(os.environ.get("TDX_L2_PORT", "7709")),
    "hq_host": os.environ.get("TDX_HQ_HOST", "119.147.212.81"),
    "hq_port": int(os.environ.get("TDX_HQ_PORT", "7709")),
    "timeout": int(os.environ.get("TDX_TIMEOUT", "5")),
    "max_retries": int(os.environ.get("TDX_MAX_RETRIES", "3")),
    "rate_limit_s": float(os.environ.get("TDX_RATE_LIMIT", "0.5")),
    "daily_max_calls": int(os.environ.get("TDX_DAILY_MAX", "10000")),
}

# === OPS 运维配置 ===
OPS = {
    "nas_host": os.environ.get("NAS_HOST", "192.168.1.4"),
    "nas_backup_path": os.environ.get("NAS_BACKUP_PATH", "/quant/backup"),
    "nas_worm_path": os.environ.get("NAS_WORM_PATH", "/quant/worm"),
    "retention_days": int(os.environ.get("BACKUP_RETENTION_DAYS", "30")),
}

# === 数据库配置 ===
DB = {
    "market_db_path": os.environ.get("MARKET_DB_PATH", None) or os.environ.get("LINGLONG_DB_PATH", None) or "data/market.db",
    "backup_db_path": os.environ.get("BACKUP_DB_PATH", "data/backup.db"),
}

# === 缓存配置 ===
CACHE = {
    "l2_cache_dir": os.environ.get("L2_CACHE_DIR", "data/cache/l2"),
    "hq_cache_dir": os.environ.get("HQ_CACHE_DIR", "data/cache/hq"),
    "cache_ttl_hours": int(os.environ.get("CACHE_TTL_HOURS", "24")),
}
'''

with open(config_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"✓ 已写入 {config_path}")
print(f"  文件大小: {os.path.getsize(config_path)} bytes")
