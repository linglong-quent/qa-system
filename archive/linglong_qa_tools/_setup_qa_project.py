"""配置 qa-system 的 linglong 项目：
1. 在 registry.yaml 里注册 linglong_local 项目
2. 创建 linglong_local.yaml 项目配置（合并 linglong 本地review-rules的配置）
"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import yaml

QA_ROOT = r"E:\WB\qa-system"
LINGLONG_ROOT = str(PROJECT_ROOT)

# === 1. 读取 linglong 本地配置 ===
print("1. 读取 linglong 本地 review-rules.yaml")
local_rr_path = os.path.join(LINGLONG_ROOT, ".ai", "config", "review-rules.yaml")
with open(local_rr_path, "r", encoding="utf-8") as f:
    local_cfg = yaml.safe_load(f)

print(f"   import_exempt: {len(local_cfg.get('import_exempt', []))} 项")
print(f"   profiles: {list(local_cfg.get('profiles', {}).keys())}")

# === 2. 读取 qa-system 的 linglong_github 配置作为模板 ===
print()
print("2. 读取 linglong_github.yaml 模板")
gh_cfg_path = os.path.join(QA_ROOT, ".ai", "projects", "linglong_github.yaml")
with open(gh_cfg_path, "r", encoding="utf-8") as f:
    gh_cfg = yaml.safe_load(f)

print(f"   checker 配置段: {len([k for k in gh_cfg.keys() if k.endswith('_check') or k in ['code_ban', 'import_boundary']])} 个")

# === 3. 创建 linglong_local.yaml ===
print()
print("3. 创建 linglong_local.yaml 项目配置")

# 以 github 配置为基础，加上本地特有的配置
local_project_cfg = dict(gh_cfg)  # 深拷贝基础配置

# 更新项目标识
local_project_cfg["version"] = "4.0"
local_project_cfg["project"] = "linglong_local"
local_project_cfg["last_updated"] = "2026-07-25"

# 更新 full profile：全部19个checker
local_project_cfg["profiles"]["full"]["checkers_on"] = [
    "inplace_check", "lookahead_check", "secret_check",
    "deadcode_check", "cyclic_check", "code_ban",
    "import_boundary", "config_audit", "quality_gates",
    "claude_validation", "codestyle", "governance",
    "securityplus", "documentation", "zeroprint",
    "customrules", "fusedetect", "docconsistency",
    "production"
]

# 新增 ci profile
local_project_cfg["profiles"]["ci"] = {
    "description": "CI 快速检查（8个核心checker）",
    "checkers_on": [
        "inplace_check", "lookahead_check", "secret_check",
        "cyclic_check", "code_ban", "import_boundary",
        "quality_gates", "zeroprint"
    ]
}

# 更新 deadcode 扫描目录（本地项目结构不同）
if "deadcode_check" in local_project_cfg:
    local_project_cfg["deadcode_check"]["scan_dirs"] = [
        "domain/", "shared/", "access/", "p0/", "backtest/", "config/"
    ]
    local_project_cfg["deadcode_check"]["entry_points"] = [
        "main.py", "run_pipeline.py", "start_all_monitors.py",
        "scripts/run_daily.py", "scripts/report_daily.py"
    ]
    # 加入 import_exempt 列表
    local_project_cfg["import_exempt"] = local_cfg.get("import_exempt", [])

# 更新 inplace / lookahead / secret / cyclic / code_ban 的扫描目录
for check_key in ["inplace_check", "lookahead_check", "secret_check", "cyclic_check", "code_ban_check"]:
    if check_key in local_project_cfg:
        local_project_cfg[check_key]["scan_dirs"] = [
            "domain/", "shared/", "access/", "p0/", "backtest/", "config/", "ops/"
        ]

# 更新 import_boundary 配置
if "import_boundary_check" in local_project_cfg:
    local_project_cfg["import_boundary_check"]["severity"] = "WARN"
    # 跨域豁免列表
    local_project_cfg["import_boundary_check"]["import_exempt"] = local_cfg.get("import_exempt", [])

# 更新 production 检查
if "production_check" in local_project_cfg:
    local_project_cfg["production_check"]["scan_dirs"] = [
        "domain/", "shared/", "p0/"
    ]
    local_project_cfg["production_check"]["severity"] = "WARN"

# 写入文件
local_proj_path = os.path.join(QA_ROOT, ".ai", "projects", "linglong_local.yaml")
with open(local_proj_path, "w", encoding="utf-8") as f:
    yaml.dump(local_project_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"   ✓ 已创建: {local_proj_path}")

# === 4. 更新 registry.yaml ===
print()
print("4. 更新 registry.yaml")

reg_path = os.path.join(QA_ROOT, ".ai", "projects", "registry.yaml")
with open(reg_path, "r", encoding="utf-8") as f:
    reg_cfg = yaml.safe_load(f)

if "linglong_local" not in reg_cfg.get("projects", {}):
    reg_cfg["projects"]["linglong_local"] = {
        "name": "玲珑量化（本地开发版）",
        "root": LINGLONG_ROOT,
        "type": "quant-trading",
        "config": "linglong_local.yaml"
    }

    with open(reg_path, "w", encoding="utf-8") as f:
        yaml.dump(reg_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print("   ✓ 已注册 linglong_local 项目")
else:
    print("   linglong_local 已注册，跳过")

print()
print("QA System 项目配置完成！")
print(f"  项目名: linglong_local")
print(f"  配置文件: {local_proj_path}")
print(f"  项目根目录: {LINGLONG_ROOT}")
