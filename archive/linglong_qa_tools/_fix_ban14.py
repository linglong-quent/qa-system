"""修复 BAN-14 孤儿模块检测逻辑
1. 增加 exempt_modules 配置（豁免的模块前缀）
2. 增加 entry_modules 配置（入口模块列表）
3. 收集引用时也扫描 scripts/ 和 tests/（用于收集引用，不检查是否孤儿）
"""

QA_FILE = r"E:\WB\qa-system\scripts\chk_codebanchecker.py"

with open(QA_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 _check_orphan_asset 函数并替换
old_func = '''    def _check_orphan_asset(self) -> List[str]:
        issues = []
        import glob as _glob

        # 使用配置的 scan_dirs，未配置时默认扫描 src/
        scan_dirs = self.config.get("scan_dirs", ["src/"])
        all_py = []
        for d in scan_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                all_py += _glob.glob(os.path.join(full, "**/*.py"), recursive=True)

        imported_modules = set()
        existing_modules = set()

        for fpath in all_py:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            rel = os.path.relpath(fpath, self.project_root)
            module_name = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
            existing_modules.add(module_name)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module)

        # 检查是否有 orphan 模块：模块的完整路径或其任何父模块被引用过
        for mod in sorted(existing_modules):
            mod_base = mod.split(".")[-1]
            if mod_base.startswith("_") or mod_base == "__init__":
                continue
            # 跳过入口脚本
            if mod_base in {"main", "__main__", "run_pipeline", "start_all_monitors"}:
                continue
            # 检查：该模块或其父模块是否被任何import引用过
            is_referenced = False
            parts = mod.split(".")
            # 从完整路径逐级往上检查前缀
            for i in range(len(parts), 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in imported_modules:
                    is_referenced = True
                    break
            # 检查：是否有import的模块以该模块为前缀（即引用了该模块下的子模块）
            if not is_referenced:
                for imp in imported_modules:
                    if imp.startswith(mod + "."):
                        is_referenced = True
                        break
            if not is_referenced:
                issues.append(
                    f"[BAN-14] 疑似未被引用的模块 '{mod}' -> " f"孤儿模块增加维护成本，确认无用后应归档或删除"
                )

        return issues'''

new_func = '''    def _check_orphan_asset(self) -> List[str]:
        issues = []
        import glob as _glob

        # 使用配置的 scan_dirs，未配置时默认扫描 src/
        scan_dirs = self.config.get("scan_dirs", ["src/"])
        # 额外用于收集引用的目录（不检查是否孤儿）
        ref_dirs = self.config.get("orphan_ref_dirs", ["scripts/", "tests/"])

        # 1. 收集需要检查的模块（scan_dirs 内的）
        check_py = []
        for d in scan_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                check_py += _glob.glob(os.path.join(full, "**/*.py"), recursive=True)

        # 2. 收集所有用于引用分析的文件（scan_dirs + ref_dirs）
        all_ref_py = list(check_py)
        for d in ref_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                all_ref_py += _glob.glob(os.path.join(full, "**/*.py"), recursive=True)

        # 3. 豁免的模块前缀（接入层、插件、已知入口）
        exempt_prefixes = set(self.config.get("orphan_exempt_prefixes", []))
        exempt_modules = set(self.config.get("orphan_exempt_modules", []))
        # 入口模块
        entry_modules = set(self.config.get("entry_modules", []))
        entry_basenames = {"main", "__main__", "run_pipeline", "start_all_monitors", "app"}

        imported_modules = set()
        existing_modules = set()

        # 收集需要检查的模块
        for fpath in check_py:
            rel = os.path.relpath(fpath, self.project_root)
            module_name = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
            existing_modules.add(module_name)

        # 收集所有引用（包括 ref_dirs 里的）
        for fpath in all_ref_py:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module)

        # 检查是否有 orphan 模块
        for mod in sorted(existing_modules):
            mod_base = mod.split(".")[-1]
            if mod_base.startswith("_") or mod_base == "__init__":
                continue
            # 跳过入口脚本
            if mod_base in entry_basenames or mod in entry_modules:
                continue
            # 跳过豁免的模块前缀
            is_exempt = False
            for prefix in exempt_prefixes:
                if mod.startswith(prefix) or mod == prefix:
                    is_exempt = True
                    break
            if is_exempt:
                continue
            # 跳过豁免的模块列表
            if mod in exempt_modules:
                continue
            # 检查：该模块或其父模块是否被任何import引用过
            is_referenced = False
            parts = mod.split(".")
            for i in range(len(parts), 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in imported_modules:
                    is_referenced = True
                    break
            # 检查：是否有import的模块以该模块为前缀
            if not is_referenced:
                for imp in imported_modules:
                    if imp.startswith(mod + "."):
                        is_referenced = True
                        break
            if not is_referenced:
                issues.append(
                    f"[BAN-14] 疑似未被引用的模块 '{mod}' -> " f"孤儿模块增加维护成本，确认无用后应归档或删除"
                )

        return issues'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(QA_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ BAN-14 检测逻辑已修复")
else:
    print("✗ 没找到旧函数，检查一下")
    # 搜索函数位置
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '_check_orphan_asset' in line:
            print(f"  L{i+1}: {line.strip()}")
