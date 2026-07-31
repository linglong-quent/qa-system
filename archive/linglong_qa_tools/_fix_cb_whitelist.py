"""给 code_ban_check.magic_whitelist 加工程常量"""
import yaml

config_path = r"E:\WB\qa-system\.ai\projects\linglong_local.yaml"

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找 code_ban_check 下的 magic_whitelist
if 'code_ban_check' in config:
    cb = config['code_ban_check']
    if 'magic_whitelist' in cb:
        current = set(cb['magic_whitelist'])
        print(f"code_ban_check.magic_whitelist: {len(current)} 个")
        
        # 新增工程常量
        new_values = [
            # 2的幂次（缓冲区大小）
            16, 32, 64, 128, 256, 512, 1024, 2048, 4096,
            # 数量级
            100, 1000, 10000, 100000, 1000000, 10000000, 100000000, 1000000000,
            100.0, 1000.0, 10000.0, 100000.0, 1000000.0, 10000000.0, 100000000.0, 1000000000.0,
            # 时间单位
            3600, 86400,
            # 交易日（已有的就不加了）
            252, 244, 250,
            # 极小值
            1e-09, 1e-06, 0.0001, 0.001,
            # uint32 max
            4294967295,
            # 常用数量
            5000, 3000, 2000, 1500,
        ]
        
        added = 0
        for v in new_values:
            if v not in current:
                current.add(v)
                added += 1
        
        # 排序：先数字（按值），再字符串
        num_list = sorted([v for v in current if isinstance(v, (int, float))], key=lambda x: (float(x), str(x)))
        str_list = sorted([v for v in current if isinstance(v, str)])
        cb['magic_whitelist'] = num_list + str_list
        
        print(f"新增 {added} 个，总计 {len(cb['magic_whitelist'])} 个")

with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("✓ 配置已更新 (code_ban_check.magic_whitelist)")
