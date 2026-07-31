"""扩大 magic_whitelist — 加入工程常量和量化通用数值"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到顶层的 magic_whitelist
if 'magic_whitelist' in config:
    current = set(config['magic_whitelist'])
    print(f"当前 magic_whitelist: {len(current)} 个")
    
    # 新增：工程常量 + 量化通用数值
    new_values = [
        # 2的幂次（缓冲区大小）
        16, 32, 64, 128, 256, 512, 1024, 2048, 4096,
        # 数量级
        100, 1000, 10000, 100000, 1000000, 10000000, 100000000, 1000000000,
        100.0, 1000.0, 10000.0, 100000.0, 1000000.0, 10000000.0, 100000000.0, 1000000000.0,
        # 时间单位（秒）
        3600, 86400,
        # 交易日
        252, 244, 250,
        # 百分比小数值
        0.01, 0.001, 0.0001, 1e-09, 1e-06,
        # 常用整数
        100,
        # uint32 max
        4294967295,
        # 5000（超时/限额类）
        5000, 3000, 2000,
    ]
    
    added = 0
    for v in new_values:
        if v not in current:
            current.add(v)
            added += 1
    
    config['magic_whitelist'] = sorted(list(current), key=lambda x: (isinstance(x, str), x))
    print(f"新增 {added} 个，总计 {len(config['magic_whitelist'])} 个")

with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✓ 配置已更新")
