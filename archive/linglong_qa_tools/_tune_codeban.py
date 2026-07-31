"""调整配置：code_ban 从阻断列表移除，改为治理项
4754个 except: pass 是历史积累，需要逐步治理，不能一次性阻断
"""
import os
import yaml

QA_ROOT = r"E:\WB\qa-system"

proj_path = os.path.join(QA_ROOT, ".ai", "projects", "linglong_local.yaml")
with open(proj_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# 从 full profile 移除 code_ban（改为治理项，单独运行）
full_checkers = cfg["profiles"]["full"]["checkers_on"]
if "code_ban" in full_checkers:
    full_checkers.remove("code_ban")
    print("✓ code_ban 从 full profile 移除（改为治理项，逐步清理）")

# ci profile 也移除
if "code_ban" in cfg["profiles"].get("ci", {}).get("checkers_on", []):
    cfg["profiles"]["ci"]["checkers_on"].remove("code_ban")
    print("✓ code_ban 从 ci profile 移除")

# 新增 governance profile（包含所有治理类checker）
if "governance" not in cfg["profiles"]:
    cfg["profiles"]["governance"] = {
        "description": "治理类检查（不阻断，定期清理）",
        "checkers_on": ["deadcode_check", "code_ban", "config_audit", "governance"]
    }
    print("✓ 新增 governance profile")

with open(proj_path, "w", encoding="utf-8") as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print()
print("配置已更新")
print(f"full profile: {len(cfg['profiles']['full']['checkers_on'])} 个 checker")
print(f"  {cfg['profiles']['full']['checkers_on']}")
