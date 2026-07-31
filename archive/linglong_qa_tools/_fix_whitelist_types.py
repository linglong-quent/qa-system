"""修复 magic_whitelist 类型问题：字符串转数值（int/float）"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

def fix_whitelist(lst):
    """把字符串数字转成数值"""
    if not lst:
        return lst
    fixed = []
    seen = set()
    for x in lst:
        if isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            val = x
        elif isinstance(x, str):
            try:
                if '.' in x or 'e' in x.lower():
                    val = float(x)
                else:
                    val = int(x)
            except ValueError:
                val = x
        else:
            val = x
        # 去重
        if val not in seen:
            seen.add(val)
            fixed.append(val)
    return fixed

# 修复顶层
old_top = config.get("magic_whitelist", [])
new_top = fix_whitelist(old_top)
print(f"顶层 magic_whitelist: {len(old_top)} -> {len(new_top)}")
config["magic_whitelist"] = new_top

# 修复 code_ban_check 下的
if "code_ban_check" in config:
    old_cb = config["code_ban_check"].get("magic_whitelist", [])
    new_cb = fix_whitelist(old_cb)
    print(f"code_ban_check magic_whitelist: {len(old_cb)} -> {len(new_cb)}")
    config["code_ban_check"]["magic_whitelist"] = new_cb

# 保存
with open(config_path, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"\n✓ 已修复并保存到 {config_path}")

# 验证
with open(config_path, "r", encoding="utf-8") as f:
    verify = yaml.safe_load(f)

print("\n验证:")
for num in [0, 1, 2, 5, 10, 20, 70, 80, 1.2, 0.85]:
    in_top = num in verify.get("magic_whitelist", [])
    in_cb = num in verify.get("code_ban_check", {}).get("magic_whitelist", [])
    print(f"  {num}: 顶层{'✓' if in_top else '✗'}  code_ban{'✓' if in_cb else '✗'}")
