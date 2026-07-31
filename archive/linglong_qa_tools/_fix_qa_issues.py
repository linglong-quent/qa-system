"""QA问题集中修复
修复项：
1. 7个BOM文件 → 移除BOM
2. config_audit缺少配置段 → 补齐
3. CLAUDE.md不存在 → 创建
4. deadcode误报 → 配置只扫描公共顶层符号
"""

from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os

ROOT = str(PROJECT_ROOT)

# === 1. 移除 BOM ===
print("=" * 50)
print("1. 移除 UTF-8 BOM")
bom_files = [
    r"domain\data\orchestrator\confidence_fusion.py",
    r"domain\decision\engines\unified_risk_fusion_backup.py",
    r"domain\decision\lib\scoring_to_position_bridge.py",
    r"domain\risk\lib\sidecar_signature.py",
    r"ops\scripts\health_check.py",
    r"p0\order_gateway.py",
    r"shared\db_conn.py",
]

fixed = 0
for f in bom_files:
    fpath = os.path.join(ROOT, f)
    if os.path.exists(fpath):
        with open(fpath, 'rb') as fh:
            data = fh.read()
        if data.startswith(b'\xef\xbb\xbf'):
            with open(fpath, 'wb') as fh:
                fh.write(data[3:])
            print(f"  ✓ {f}")
            fixed += 1
print(f"  共修复 {fixed} 个BOM文件")

# === 2. 补齐 review-rules.yaml 的配置段 ===
print()
print("=" * 50)
print("2. 补齐 review-rules.yaml 配置段")

review_path = os.path.join(ROOT, ".ai", "config", "review-rules.yaml")
with open(review_path, "r", encoding="utf-8") as f:
    content = f.read()

# 检查哪些段缺失
missing_sections = []
for section in [
    "inplace_check", "lookahead_check", "secret_check",
    "cyclic_check", "code_ban_check", "import_boundary_check",
]:
    if f"{section}:" not in content:
        missing_sections.append(section)

if missing_sections:
    # 在deadcode_check后面追加
    append_text = "\n# 其他checker默认配置\n"
    if "inplace_check" in missing_sections:
        append_text += "inplace_check:\n  enabled: true\n  severity: INFO\n"
    if "lookahead_check" in missing_sections:
        append_text += "lookahead_check:\n  enabled: true\n  severity: INFO\n  scan_dirs: [\"domain/\", \"shared/\", \"backtest/\"]\n"
    if "secret_check" in missing_sections:
        append_text += "secret_check:\n  enabled: true\n  severity: BLOCKER\n"
    if "cyclic_check" in missing_sections:
        append_text += "cyclic_check:\n  enabled: true\n  severity: WARN\n  scan_dirs: [\"domain/\", \"shared/\"]\n"
    if "code_ban_check" in missing_sections:
        append_text += "code_ban_check:\n  enabled: true\n  severity: BLOCKER\n"
    if "import_boundary_check" in missing_sections:
        append_text += "import_boundary_check:\n  enabled: true\n  severity: WARN\n"

    # 找到最后一行追加
    with open(review_path, "a", encoding="utf-8") as f:
        f.write(append_text)
    print(f"  ✓ 补齐 {len(missing_sections)} 个配置段: {', '.join(missing_sections)}")
else:
    print("  所有配置段已存在")

# === 3. 创建 CLAUDE.md ===
print()
print("=" * 50)
print("3. 创建 CLAUDE.md（AI编码约束）")

claude_path = os.path.join(ROOT, "CLAUDE.md")
if not os.path.exists(claude_path):
    claude_content = """# CLAUDE.md — AI 编码行为准则

## 核心原则

1. **零污染原则**: 不修改不在任务范围内的代码
2. **先测试再改动**: 任何改动必须有对应测试验证
3. **保留原有设计**: 不重构未经要求的代码结构
4. **异常安全**: 所有边界函数必须有 try/except 保护

## 禁止项

- 禁止使用 `eval()` / `exec()`
- 禁止硬编码密钥 / 密码 / API Key
- 禁止裸 `except:`（必须捕获具体异常）
- 禁止 `print()` 调试（用 logging）
- 禁止 inplace=True 的 pandas 操作（除非明确需要）

## 必须项

- 所有公共函数必须有 docstring
- 所有外部调用必须设 timeout
- 所有文件使用 UTF-8 无 BOM 编码
- 所有路径使用 os.path / Path，不硬编码

## 架构约束

- domain层只能向下依赖，不能反向依赖
- 跨层调用必须通过 api/ 目录
- 数据层 → 因子层 → 认知层 → 决策层 → 执行层（单向）
"""
    with open(claude_path, "w", encoding="utf-8") as f:
        f.write(claude_content)
    print("  ✓ CLAUDE.md 已创建")
else:
    print("  CLAUDE.md 已存在")

# === 4. 修正 deadcode 配置（减少误报）===
print()
print("=" * 50)
print("4. 优化 deadcode 配置（减少误报）")

# 读取并更新deadcode配置

with open(review_path, "r", encoding="utf-8") as f:
    content = f.read()

# 增加 entry_points 列表，让deadcode checker知道入口
old_dc = '''deadcode_check:
  scan_dirs:
    - "domain/"
    - "shared/"
    - "access/"
    - "p0/"
    - "backtest/"
    - "config/"
  entry_points:
    - "main.py"
    - "cli.py"
  exempt_names:
    - "main"
    - "__init__"
    - "__main__"
    - "__version__"
    - "__all__"
    - "app"
    - "run"'''

new_dc = '''deadcode_check:
  enabled: true
  severity: WARN
  scan_dirs:
    - "domain/"
    - "shared/"
    - "access/"
    - "p0/"
    - "backtest/"
    - "config/"
  entry_points:
    - "main.py"
    - "run_pipeline.py"
    - "start_all_monitors.py"
    - "scripts/run_daily.py"
    - "scripts/report_daily.py"
  scan_public_only: true
  exempt_names:
    - "main"
    - "__init__"
    - "__main__"
    - "__version__"
    - "__all__"
    - "app"
    - "run"
    - "logger"
    - "setup"'''

if old_dc in content:
    content = content.replace(old_dc, new_dc)
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  ✓ deadcode 配置已优化")
else:
    print("  deadcode 配置格式不同，跳过")

print()
print("=" * 50)
print("所有修复完成！")
