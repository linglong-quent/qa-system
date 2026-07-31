import logging

logger = logging.getLogger(__name__)
config_path = r'E:\WB\QA-System\.ai\projects\linglong_local.yaml'
with open(config_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 手动提取两个 magic_whitelist
# 第一个在第 286 行 (0-indexed: 285)
# 第二个在第 594 行 (0-indexed: 593)

def extract_list(start_line_idx, lines):
    """从指定行开始提取 YAML 列表，直到下一个同级键"""
    items = []
    i = start_line_idx
    # 跳过第一行（键名）
    i += 1
    # 父级缩进
    parent_indent = len(lines[start_line_idx]) - len(lines[start_line_idx].lstrip())
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 空行跳过
        if not stripped:
            i += 1
            continue
        
        # 计算当前行缩进
        current_indent = len(line) - len(line.lstrip())
        
        # 如果是列表项且缩进比父级大（或等于，因为-也算缩进的一部分）
        if stripped.startswith('- ') and current_indent >= parent_indent:
            val_str = stripped[2:].strip()
            # 转换为数字
            try:
                if '.' in val_str or 'e' in val_str.lower():
                    val = float(val_str)
                else:
                    val = int(val_str)
                items.append(val)
            except ValueError:
                logger.exception("Unexpected error")
                pass
            i += 1
        else:
            break
    
    return items

# 第一个 magic_whitelist (第 286 行，0-indexed 285)
mw1 = extract_list(285, lines)
print(f'第一个 magic_whitelist (286行): {len(mw1)} 个元素')

# 第二个 magic_whitelist (第 594 行，0-indexed 593)
mw2 = extract_list(593, lines)
print(f'第二个 magic_whitelist (594行): {len(mw2)} 个元素')

# 找差集
set1 = set(mw1)
set2 = set(mw2)

only_in_1 = set1 - set2
only_in_2 = set2 - set1

print(f'\n只在第一个中的（新增的）: {len(only_in_1)} 个')
print(sorted(only_in_1))

print(f'\n只在第二个中的: {len(only_in_2)} 个')
print(sorted(only_in_2))
