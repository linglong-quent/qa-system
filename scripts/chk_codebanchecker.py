import ast, os, re
from typing import List
from chk_codeban_b import CodeBanMid


class CodeBanChecker(CodeBanMid):
    def check(self) -> tuple:
        """执行所有 code-ban 检查，返回 (errors_count, issues_list)"""
        issues = []
        py_files = self._collect_py_files()
        for check_method in [
            self._check_except_pass,
            self._check_cross_layer,
            self._check_core_import_boundary,
            self._check_hardcoded_path,
            self._check_magic_numbers,
            self._check_hardcoded_ip,
            self._check_eval_exec,
            self._check_bare_db_connect,
            self._check_deprecated_import,
            self._check_large_class,
            self._check_log_structure,
            self._check_lookahead,
        ]:
            try:
                issues += check_method(py_files)
            except Exception as e:
                issues.append(f"[BAN-ERR] {check_method.__name__}: {e}")
        # Special: _check_orphan_asset takes no args
        try:
            issues += self._check_orphan_asset()
        except Exception as e:
            issues.append(f"[BAN-ERR] _check_orphan_asset: {e}")
        return len(issues), issues

    def _check_hardcoded_ip(self, py_files: List[str]) -> List[str]:
        issues = []
        IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    ips = IP_PATTERN.findall(node.value)
                    for ip in ips:
                        if ip not in ("0.0.0.0", "127.0.0.1", "255.255.255.255"):
                            issues.append(
                                f"[BAN-7] {fpath}:{node.lineno} 硬编码 IP '{ip}' -> " f"应从配置文件读取，参考 CWE-200"
                            )
        return issues

    # ─── 规则 8: eval/exec 动态执行（源自 KUN G5A-004 → OWASP 注入）───
    def _check_eval_exec(self, py_files: List[str]) -> List[str]:
        issues = []
        DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in DANGEROUS_CALLS:
                        issues.append(
                            f"[BAN-8] {fpath}:{node.lineno} {node.func.id}() 动态执行 -> "
                            f"禁止动态执行不可信代码，OWASP 注入类风险"
                        )
        return issues

    # ─── 规则 9: 裸 sqlite3.connect（源自 KUN G5A-005 → 安全配置）───
    def _check_bare_db_connect(self, py_files: List[str]) -> List[str]:
        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "connect" and node.func.value.id in ("sqlite3",):
                        issues.append(
                            f"[BAN-9] {fpath}:{node.lineno} 裸 sqlite3.connect() -> "
                            f"应通过配置化的 db_manager 或 db_config 连接数据库"
                        )
        return issues

    # ─── 规则 10: 超大类 >300 行（源自 KUN G5A-007 → SRP 单一职责）───
    def _check_large_class(self, py_files: List[str]) -> List[str]:
        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if hasattr(node, "end_lineno") and node.end_lineno:
                        class_lines = node.end_lineno - node.lineno
                    else:
                        class_lines = 0
                    if class_lines > 300:
                        issues.append(
                            f"[BAN-10] {fpath}:{node.lineno} 类 {node.name} "
                            f"({class_lines} 行 > 300) -> "
                            f"超大类违反 SRP 单一职责原则，建议拆分为多个类"
                        )
        return issues

    # ─── 规则 11: 回测未来函数引用（源自 KUN G5A-009 → 量化 lookahead 防偏）───
    def _check_lookahead(self, py_files: List[str]) -> List[str]:
        issues = []
        LOOKAHEAD_PATTERNS = [r"shift\(\s*-\d+\s*\)", r"\.iloc\[\s*:\s*-?\d+\s*\]"]
        for fpath in py_files:
            rel = os.path.relpath(fpath, self.project_root)
            if "backtest" not in rel.lower() and "回测" not in rel.replace("_deprecated", ""):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            for pattern in LOOKAHEAD_PATTERNS:
                for m in re.finditer(pattern, content):
                    line_num = content[: m.start()].count("\n") + 1
                    issues.append(
                        f"[BAN-11] {fpath}:{line_num} 疑似未来函数引用 "
                        f"'{m.group()}' -> "
                        f"回测中使用 shift(-N) 引用未来数据会导致 lookahead bias"
                    )
        return issues

    # ─── 规则 12: 废弃 import（检测导入 _deprecated/已迁移模块，源自 KUN G5A-010）───
    def _check_deprecated_import(self, py_files: List[str]) -> List[str]:
        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if "_deprecated" in alias.name or "deprecated" in alias.name.lower():
                            issues.append(
                                f"[BAN-12] {fpath}:{node.lineno} 导入已废弃模块 "
                                f"'{alias.name}' -> "
                                f"应移除对 _deprecated/ 模块的引用"
                            )
        return issues

    # ─── 规则 13: 日志结构校验（源自 KUN skill_log_structure → 12-Factor App / OWASP 日志审计）───
    LOG_REQUIRED_FIELDS = {
        "trade": ["order_id", "symbol", "price", "volume", "side", "timestamp", "trace_id"],
        "risk": ["check_type", "symbol", "result", "timestamp", "trace_id"],
        "signal": ["signal_name", "symbol", "value", "timestamp", "trace_id"],
        "data": ["source", "symbol", "field", "timestamp"],
    }

    def _check_log_structure(self, py_files: List[str]) -> List[str]:
        issues = []
        for fpath in py_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            for log_type, required in self.LOG_REQUIRED_FIELDS.items():
                if f"log_{log_type}" in content.lower() or f"{log_type}_log" in content.lower():
                    for field in required:
                        if field not in content.lower():
                            rel = os.path.relpath(fpath, self.project_root)
                            issues.append(
                                f"[BAN-13] {rel} 日志类型 '{log_type}' 缺少必需字段 "
                                f"'{field}' -> "
                                f"参考 12-Factor App 日志规范，交易日志必须包含 {', '.join(required)}"
                            )
        return issues

    # ─── 规则 14: 未使用资产/孤儿文件检测 ───
    def _check_orphan_asset(self) -> List[str]:
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
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        imported_modules.add(alias.name.split(".")[0])

        # 检查是否有 orphan 模块
        for mod in sorted(existing_modules):
            mod_base = mod.split(".")[-1]
            if mod_base.startswith("_") or mod_base == "__init__":
                continue
            if mod_base not in imported_modules and mod_base not in {"main"}:
                issues.append(
                    f"[BAN-14] 疑似未被引用的模块 '{mod}' -> " f"孤儿模块增加维护成本，确认无用后应归档或删除"
                )

        return issues
