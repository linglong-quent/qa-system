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
        # 浏览器 UA 中的版本号（如 Chrome/120.0.0.0）不是 IP，需跳过
        UA_MARKERS = ("mozilla", "chrome/", "safari/", "webkit", "khtml")
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    low = node.value.lower()
                    if any(m in low for m in UA_MARKERS):
                        continue
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
        # 豁免路径片段: 模拟器动态装配引擎/迁移工具/因子审计 (动态加载项目内已知模块,
        # 源码均带 # noqa: BAN-8 注释声明有意为之; 生产业务代码不豁免)
        exempt = tuple(self.config.get("dynamic_exec_exempt_substrings", []))
        for fpath in py_files:
            if exempt and any(e in fpath for e in exempt):
                continue
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
        # 豁免路径片段: SQLite 专项工具/迁移脚本/测试 (操作对象即 SQLite 源库,
        # 裸 connect 是行业标准做法; 生产业务代码不豁免)
        exempt = tuple(self.config.get("bare_connect_exempt_substrings", []))
        for fpath in py_files:
            if exempt and any(e in fpath for e in exempt):
                continue
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if (
                        node.func.attr == "connect"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id in ("sqlite3",)
                    ):
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
        """检测未被任何模块引用的孤儿模块。

        引用收集规则（避免误报）:
          - `import a.b.c`         → 引用 a / a.b / a.b.c（全部前缀）
          - `from a.b.c import X`  → 引用 a.b.c（模块本身）+ 符号 X
          - `from . import X`      → 相对导入，引用符号 X
        引用收集范围 = scan_dirs + ref_dirs(scripts/tests)，防止仅被
        脚本/测试引用的业务模块被误判为孤儿。
        """
        issues = []
        import glob as _glob

        scan_dirs = self.config.get("scan_dirs", ["src/"])
        # 兼容两种配置键: orphan_ref_dirs (框架约定) / ref_dirs (通用键)
        ref_dirs = list(dict.fromkeys(
            scan_dirs
            + self.config.get("orphan_ref_dirs", self.config.get("ref_dirs", ["scripts", "tests"]))
        ))
        all_py = []
        for d in scan_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                all_py += _glob.glob(os.path.join(full, "**/*.py"), recursive=True)
        ref_py = []
        for d in ref_dirs:
            full = os.path.join(self.project_root, d)
            if os.path.isdir(full):
                ref_py += _glob.glob(os.path.join(full, "**/*.py"), recursive=True)
        # 项目根级入口脚本 (run_pipeline.py / start_all_monitors.py 等) 也是引用来源,
        # 缺失会导致仅被入口脚本引用的业务模块被误判为孤儿
        ref_py += _glob.glob(os.path.join(self.project_root, "*.py"))

        # 被引用的模块路径（完整路径 + 祖先前缀）与叶子符号名
        referenced_modules: set = set()
        referenced_leaves: set = set()

        def _record_import(module: str) -> None:
            """`import a.b.c` / `from a.b.c import X` 均视为引用 a.b.c 及其祖先包"""
            parts = module.split(".")
            for i in range(1, len(parts) + 1):
                referenced_modules.add(".".join(parts[:i]))

        def _module_of(fpath: str) -> str:
            """文件相对路径 → 点分模块名 (__init__.py 视作包本身)"""
            rel = os.path.relpath(fpath, self.project_root).replace(os.sep, ".")
            mod = rel[:-3] if rel.endswith(".py") else rel
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            return mod

        def _resolve_import(node, current_mod: str, is_init: bool) -> str:
            """相对导入 (from .x / from ..x) 解析为完整模块路径。

            修复误报: 相对导入的 node.module 只有短名 (如 'daily_mixin'),
            不解析则与 existing_modules 的完整路径 (domain.data.datamirror.daily_mixin)
            永远不匹配, 导致 datamirror mixin 等模块被误判为孤儿。
            """
            if node.level == 0:
                return node.module or ""
            pkg = current_mod if is_init else (current_mod.rpartition(".")[0] or current_mod)
            m = node.module or ""
            try:
                import importlib.util as _ilu
                # AST 的 node.module 不含前导点, 需按 level 补点 ('.daily_mixin' / '..foo')
                return _ilu.resolve_name("." * node.level + m, pkg)
            except (ImportError, ValueError):
                # 兜底: 手动拼接 (按 level 逐级上溯)
                parts = pkg.split(".")
                for _ in range(node.level - 1):
                    if parts:
                        parts.pop()
                return ".".join(parts + [m]) if m else ".".join(parts)

        for fpath in ref_py:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            current_mod = _module_of(fpath)
            is_init = os.path.basename(fpath) == "__init__.py"
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        _record_import(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    resolved = _resolve_import(node, current_mod, is_init)
                    if resolved:
                        _record_import(resolved)
                    for alias in node.names:
                        referenced_leaves.add(alias.asname or alias.name)

        existing_modules = set()
        for fpath in all_py:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            rel = os.path.relpath(fpath, self.project_root)
            module_name = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
            existing_modules.add(module_name)

        exempt_prefixes = tuple(self.config.get("orphan_exempt_prefixes", []))

        # 检查是否有 orphan 模块
        for mod in sorted(existing_modules):
            mod_base = mod.split(".")[-1]
            if mod_base.startswith("_") or mod_base == "__init__":
                continue
            if mod_base in referenced_leaves or mod_base in {"main"}:
                continue
            if mod in referenced_modules:
                continue
            if exempt_prefixes and mod.startswith(exempt_prefixes):
                continue
            issues.append(
                f"[BAN-14] 疑似未被引用的模块 '{mod}' -> " f"孤儿模块增加维护成本，确认无用后应归档或删除"
            )

        return issues
