"""修复 BAN-5 checker 的 3 个实现bug：
1. 不识别 AnnAssign（带类型注解的赋值语句）
2. 字典值里的数字也算魔法数字
3. 列表/元组/集合里的常量表也算魔法数字
"""

file_path = r"E:\WB\qa-system\scripts\chk_codeban_b.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    def _check_magic_numbers(self, py_files: List[str]) -> List[str]:
        """检测魔法数字（不在白名单中的数值字面量）"""
        import ast as ast_module

        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            self._annotate_parents(tree)
            for node in ast_module.walk(tree):
                if not isinstance(node, ast_module.Constant):
                    continue
                val = node.value
                # 只检查 int 和 float
                if not isinstance(val, (int, float)):
                    continue
                # 跳过 bool（Python 中 bool 是 int 子类）
                if isinstance(val, bool):
                    continue
                # 跳过白名单
                if val in self.magic_whitelist:
                    continue
                # 跳过 __main__ 块
                if self._is_in_main_block(node):
                    continue
                # 跳过函数默认参数（ast.arguments.defaults 中的值）
                parent = getattr(node, "parent", None)
                if parent and isinstance(parent, (ast_module.arguments, ast_module.arg)):
                    continue
                # 跳过赋值语句中变量名包含特定关键字的（如 _PORT, _TIMEOUT, _MAX, _THRESHOLD）
                if parent and isinstance(parent, ast_module.Assign):
                    _is_named_constant = False
                    for target in parent.targets:
                        if isinstance(target, ast_module.Name):
                            name = target.id.upper()
                            if any(kw in name for kw in self.magic_keyword_whitelist):
                                _is_named_constant = True
                                break
                    if _is_named_constant:
                        continue
                # 跳过关键字参数（arg='value'）
                if parent and isinstance(parent, ast_module.keyword):
                    continue

                issues.append(
                    f"[BAN-5] {fpath}:{node.lineno} 魔法数字 {val} -> "
                    f"应提取为命名常量 (e.g. MAX_RETRY_COUNT = {val})"
                )
        return issues'''

new = '''    def _check_magic_numbers(self, py_files: List[str]) -> List[str]:
        """检测魔法数字（不在白名单中的数值字面量）"""
        import ast as ast_module

        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            self._annotate_parents(tree)
            for node in ast_module.walk(tree):
                if not isinstance(node, ast_module.Constant):
                    continue
                val = node.value
                # 只检查 int 和 float
                if not isinstance(val, (int, float)):
                    continue
                # 跳过 bool（Python 中 bool 是 int 子类）
                if isinstance(val, bool):
                    continue
                # 跳过白名单
                if val in self.magic_whitelist:
                    continue
                # 跳过 __main__ 块
                if self._is_in_main_block(node):
                    continue
                parent = getattr(node, "parent", None)
                # 跳过函数默认参数
                if parent and isinstance(parent, (ast_module.arguments, ast_module.arg)):
                    continue
                # 跳过关键字参数
                if parent and isinstance(parent, ast_module.keyword):
                    continue
                # 跳过字典值（配置字典中的值不算魔法数字）
                if parent and isinstance(parent, ast_module.Dict):
                    idx = None
                    for i, v in enumerate(parent.values):
                        if v is node:
                            idx = i
                            break
                    if idx is not None:
                        continue
                # 跳过列表/元组/集合中的元素（常量表不算魔法数字）
                if parent and isinstance(parent, (ast_module.List, ast_module.Tuple, ast_module.Set)):
                    continue
                # 跳过赋值语句中变量名包含特定关键字的（含 AnnAssign）
                if parent and isinstance(parent, (ast_module.Assign, ast_module.AnnAssign)):
                    _is_named_constant = False
                    if isinstance(parent, ast_module.Assign):
                        targets = parent.targets
                    else:
                        targets = [parent.target]
                    for target in targets:
                        if isinstance(target, ast_module.Name):
                            name = target.id.upper()
                            if any(kw in name for kw in self.magic_keyword_whitelist):
                                _is_named_constant = True
                                break
                    if _is_named_constant:
                        continue

                issues.append(
                    f"[BAN-5] {fpath}:{node.lineno} 魔法数字 {val} -> "
                    f"应提取为命名常量 (e.g. MAX_RETRY_COUNT = {val})"
                )
        return issues'''

if old in content:
    content = content.replace(old, new)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ BAN-5 checker 已修复")
else:
    print("✗ 没找到旧代码，可能已经改过了")
    # 检查一下现有的
    if "AnnAssign" in content:
        print("  (AnnAssign 已存在，可能之前修过)")
    if "ast_module.Dict" in content:
        print("  (字典值跳过 已存在)")
