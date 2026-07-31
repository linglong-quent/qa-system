"""验证配置加载是否正确"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, "r", encoding="utf-8") as f:
    full_config = yaml.safe_load(f)

codeban_config = full_config.get("code_ban_check", {})
print("=== code_ban_check 配置 ===")
whitelist = codeban_config.get("magic_whitelist", [])
print(f"magic_whitelist 数量: {len(whitelist)}")
print(f"前15个: {list(whitelist)[:15]}")

# 检查类型
print(f"\n元素类型样本:")
for i, x in enumerate(list(whitelist)[:5]):
    print(f"  [{i}] {repr(x)} -> {type(x).__name__}")

# 检查关键数字
key_nums = [70, 80, 55, 65, 35, 1.2, 0.85]
print(f"\n关键数字白名单检查:")
for num in key_nums:
    in_list = num in whitelist or str(num) in whitelist or float(num) in whitelist
    print(f"  {num}: {'✓' if in_list else '✗'}")

# 顶层配置
print(f"\n=== 顶层 magic_whitelist ===")
top_whitelist = full_config.get("magic_whitelist", [])
print(f"数量: {len(top_whitelist)}")
print(f"前15个: {list(top_whitelist)[:15]}")

# 检查 magic_keyword_whitelist
kw_whitelist = codeban_config.get("magic_keyword_whitelist", [])
print(f"\n=== magic_keyword_whitelist ===")
print(f"数量: {len(kw_whitelist)}")
print(f"前20个: {list(kw_whitelist)[:20]}")
