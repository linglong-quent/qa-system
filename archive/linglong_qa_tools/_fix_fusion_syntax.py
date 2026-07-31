"""修复 fusion.py 语法错误"""

path = r"E:\WB\linglong\domain\factor\engines\fusion.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到第82行附近的问题
# 第82行是注释掉的半截代码，后面跟着一个悬空的tuple
# 修复：把这整个块改为正确的 try-except import 模式

# 找到问题行
for i, line in enumerate(lines):
    if "config stub" in line:
        # 从这行开始，到对应的右括号结束，整个重构
        start = i
        # 找下一个except
        end = start
        for j in range(start, len(lines)):
            if "except Exception:" in lines[j] and j > start + 5:
                end = j
                break
        
        print(f"问题区域: 行 {start+1} - {end+1}")
        print("原内容:")
        for k in range(start, min(end+2, len(lines))):
            print(f"  {k+1}: {lines[k].rstrip()}")
        
        # 替换为正确的 import 模式
        new_block = [
            "        # 尝试从 _core/config.py 导入阈值（如果存在）\n",
            "        try:\n",
            "            from _core.config import (\n",
            "                ARBITRATOR_ENABLED,\n",
            "                AUTO_SYNC_ENABLED,\n",
            "                COVERAGE_MIN_PCT,\n",
            "                DD_TOLERANCE,\n",
            "                MAX_CANDIDATE_POOL,\n",
            "                RET_TOLERANCE,\n",
            "            )\n",
            "\n",
        ]
        
        # 保留后面的 merged 赋值部分
        # 找 merged["_py_thresholds"] 开始的位置
        merge_start = end
        for j in range(start, end + 10):
            if j < len(lines) and 'merged["_py_thresholds"]' in lines[j]:
                merge_start = j
                break
        
        print(f"\nmerged赋值从行 {merge_start+1} 开始")
        
        # 构建新内容
        new_lines = lines[:start] + new_block + lines[merge_start:]
        
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        print("\n✓ 语法已修复")
        break

# 验证
import ast
with open(path, "r", encoding="utf-8") as f:
    source = f.read()
try:
    ast.parse(source)
    print("✓ 语法验证通过")
except SyntaxError as e:
    print(f"✗ 仍有语法错误: line {e.lineno}: {e.msg}")
