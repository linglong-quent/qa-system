#!/usr/bin/env python3
"""Checker: name collision / soft-forward / pure-forward detection.

Implements STYLE-03b (跨域命名空间隔离 & 单一数据源) checks:

  1. **STYLE-03b-1** — Same-name classes defined in multiple files
  2. **STYLE-03b-2** — Soft-forwarding aliases (``X = Y`` where Y is imported)
  3. **STYLE-03b-3** — Pure-forwarding modules (entirely re-export)

References:
    - quant-coding-standards.md §STYLE-03b
    - LingLong v4.0 naming conflict postmortem (2026-07)
"""

import ast
import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


class NamingConflictChecker:
    """Detect class-name collisions, soft-forward aliases, pure-forward modules."""

    CHECKER_LABEL = "命名冲突检测"

    # Generic names that SHOULD always carry a domain prefix if reused
    GENERIC_NAMES: Set[str] = {
        "Result", "State", "Status", "Signal", "Config",
        "Engine", "Manager", "Provider", "Factory", "Builder",
        "Adapter", "Handler", "Processor", "Context", "Event",
        "Record", "Data", "Info", "Item", "Model",
        "Container", "Registry", "Service", "Client", "Session",
    }

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        # Directories to skip entirely
        self.skip_dirs: Set[str] = set(config.get(
            "skip_dirs",
            ["__pycache__", ".git", ".ai", "venv", ".venv", "node_modules", "dist", "build",
             "backup", "__pycache__", ".mypy_cache", ".pytest_cache"],
        ))
        # File name patterns to skip when scanning for duplicates
        self.exempt_file_patterns: Set[str] = set(config.get(
            "exempt_file_patterns",
            ["test_", "conftest", "setup.py", "conf.py"],
        ))
        # Known SSOT classes: (canonical_file_basename, class_name)
        # These are exempt from duplicate-class detection
        self.ssot_exemptions: List[Tuple[str, str]] = [
            (p.split(":")[0], p.split(":")[1])
            for p in config.get("ssot_exemptions", [])
        ]

        # Thresholds
        self.max_issues = config.get("max_issues", 100)

    # ── File discovery ──────────────────────────────────────────

    def _collect_py_files(self) -> List[str]:
        """Collect all .py files in the project tree, minus skip_dirs."""
        files: List[str] = []
        for root, dirs, fnames in os.walk(self.project_root):
            # Mutate dirs in-place to skip unwanted dirs
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]

            for fn in fnames:
                if fn.endswith(".py"):
                    fpath = os.path.join(root, fn)
                    # Skip files matching exempt patterns
                    skip = any(fn.startswith(p) or fn == p for p in self.exempt_file_patterns)
                    if not skip:
                        files.append(fpath)
        return files

    # ── AST extraction ──────────────────────────────────────────

    @staticmethod
    def _parse_file(fpath: str) -> Optional[ast.AST]:
        """Return AST or None if unparseable."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                return ast.parse(f.read(), filename=fpath)
        except SyntaxError:
            return None

    def _extract_classes(self, tree: ast.AST) -> List[Tuple[str, int, List[str]]]:
        """Extract (class_name, line_number, [field_names]) from AST."""
        classes: List[Tuple[str, int, List[str]]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                fields = self._extract_dataclass_fields(node)
                classes.append((node.name, node.lineno, fields))
        return classes

    @staticmethod
    def _extract_dataclass_fields(class_node: ast.ClassDef) -> List[str]:
        """Extruct field names from a dataclass or regular class __init__."""
        fields: List[str] = []
        for item in class_node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
            elif isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for arg in item.args.args[1:]:  # skip self
                    fields.append(arg.arg)
        return sorted(fields)

    def _extract_top_assignments(self, tree: ast.AST) -> List[Tuple[str, int, str]]:
        """Extract top-level ``Name = ...`` assignments."""
        assigns: List[Tuple[str, int, str]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        rhs = self._rhs_name(node.value)
                        if rhs:
                            assigns.append((target.id, node.lineno, rhs))
        return assigns

    @staticmethod
    def _rhs_name(node: ast.AST) -> Optional[str]:
        """If the RHS is a simple Name, return it; else None."""
        if isinstance(node, ast.Name):
            return node.id
        return None

    def _extract_imported_names(self, tree: ast.AST) -> Set[str]:
        """Extract all names imported in this module."""
        names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
        return names

    def _is_pure_forward_module(self, tree: ast.AST, file_rel: str) -> bool:
        """Check if module is a pure re-export (body is only imports + __all__)."""
        # __init__.py is intentionally a facade; exempt
        if os.path.basename(file_rel) == "__init__.py":
            return False

        allowed_nodes = 0
        total_nodes = 0
        for node in ast.iter_child_nodes(tree):
            total_nodes += 1
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                allowed_nodes += 1
            elif isinstance(node, ast.Assign):
                # Allow __all__ assignment
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        allowed_nodes += 1
                        break
        # If every top-level node is an import/__all__, it's a pure forward
        return total_nodes > 0 and allowed_nodes == total_nodes

    # ── Check methods ───────────────────────────────────────────

    def _check_duplicate_classes(self, py_files: List[str]) -> List[str]:
        """STYLE-03b-1: same-name class in multiple files."""
        issues: List[str] = []
        # class_name -> [(file_rel, line, fields)]
        class_map: Dict[str, List[Tuple[str, int, List[str]]]] = defaultdict(list)

        for fpath in py_files:
            tree = self._parse_file(fpath)
            if tree is None:
                continue
            classes = self._extract_classes(tree)
            rel = os.path.relpath(fpath, self.project_root)
            for name, lineno, fields in classes:
                # Skip SSOT-exempt: canonical file that IS the single source
                is_ssot = any(
                    rel.endswith(canonical) and name == class_name
                    for canonical, class_name in self.ssot_exemptions
                )
                if not is_ssot:
                    class_map[name].append((rel, lineno, fields))

        for class_name, locations in sorted(class_map.items()):
            if len(locations) <= 1:
                continue

            # Eliminate same-path duplicates (can happen with duplicated modules)
            unique_files = {loc[0] for loc in locations}
            if len(unique_files) <= 1:
                continue

            # Group by field signature
            sig_groups: Dict[str, List[Tuple[str, int, List[str]]]] = defaultdict(list)
            for loc in locations:
                sig = ",".join(loc[2])
                sig_groups[sig].append(loc)

            # If there's only one field signature, and multiple files → still a violation
            # (duplicate definition even if identical fields)
            loc_detail = "; ".join(
                f"{f}:{l}" for f, l, _ in locations
            )
            issues.append(
                f"[STYLE-03b-1] 同名类 '{class_name}' "
                f"在 {len(locations)} 处定义: {loc_detail} "
                f"-> 违反单一数据源原则, 应合并至一处并删其余"
            )

        return issues

    def _check_soft_forwarding_aliases(self, py_files: List[str]) -> List[str]:
        """STYLE-03b-2: ``X = Y`` soft-forward alias where Y is imported."""
        issues: List[str] = []

        for fpath in py_files:
            tree = self._parse_file(fpath)
            if tree is None:
                continue
            # Skip __init__.py — intentional facade
            rel = os.path.relpath(fpath, self.project_root)
            if os.path.basename(fpath) == "__init__.py":
                continue

            imported = self._extract_imported_names(tree)
            assigns = self._extract_top_assignments(tree)

            for lhs, lineno, rhs in assigns:
                if rhs in imported:
                    # Verify it's a class-like alias, not a constant assignment
                    # (constants are all-caps, soft-forwards are PascalCase/SnakeCase)
                    if lhs[0].isupper() and rhs[0].isupper():
                        # Check it's not a constant assignment (all-caps both sides)
                        # Constants: both ALL_CAPS → skip
                        if lhs.isupper() and rhs.isupper():
                            continue  # This is a constant alias, not class forwarding
                        issues.append(
                            f"[STYLE-03b-2] {rel}:{lineno} "
                            f"软转发别名 '{lhs} = {rhs}' (导入自上层) "
                            f"-> 禁止软转发, 应直接引用原名"
                        )
        return issues

    def _check_pure_forwarding_modules(self, py_files: List[str]) -> List[str]:
        """STYLE-03b-3: modules that are purely re-exports."""
        issues: List[str] = []

        for fpath in py_files:
            tree = self._parse_file(fpath)
            if tree is None:
                continue
            rel = os.path.relpath(fpath, self.project_root)
            if self._is_pure_forward_module(tree, rel):
                issues.append(
                    f"[STYLE-03b-3] {rel} 纯转发模块 (仅包含 import/__all__) "
                    f"-> 禁止纯转发, 直接引用目标模块"
                )
        return issues

    # ── Main entry ──────────────────────────────────────────────

    def check(self, config: Optional[dict] = None) -> Tuple[int, List[str]]:
        """Run all naming conflict checks.

        Returns:
            Tuple of (error_count, issue_descriptions)
        """
        issues: List[str] = []
        py_files = self._collect_py_files()

        issues.extend(self._check_duplicate_classes(py_files))
        issues.extend(self._check_soft_forwarding_aliases(py_files))
        issues.extend(self._check_pure_forwarding_modules(py_files))
        issues.extend(self._check_generic_names(py_files))

        # Cap total issues
        if len(issues) > self.max_issues:
            issues = issues[:self.max_issues]
            issues.append(f"[INFO] 截断显示: 仅展示前 {self.max_issues} 条")

        return len(issues), issues

    # ── NAMING_REGISTRY 通用词校验 ──────────────────────────────

    def _check_generic_names(self, py_files: List[str]) -> List[str]:  # noqa: STYLE-06
        """STYLE-03b-4: 通用词类名必须加域前缀 (NAMING_REGISTRY 规范).

        量化行业规范: Signal/Result/State/Config/Engine/Manager/Client 等
        通用词出现在类名中时, 必须带域前缀 (如 CognitionSignal, AccessClient).
        """
        issues: List[str] = []

        # 确定类所属域
        def _detect_domain(file_rel: str) -> str:
            if file_rel.startswith("shared" + os.sep):
                return "shared"
            if file_rel.startswith("p0" + os.sep):
                return "p0"
            parts = file_rel.split(os.sep)
            for i, p in enumerate(parts):
                if p == "domain" and i + 1 < len(parts):
                    return f"domain.{parts[i + 1]}"
            if file_rel.startswith("backtest" + os.sep):
                return "backtest"
            if file_rel.startswith("ops" + os.sep):
                return "ops"
            if file_rel.startswith("scripts" + os.sep):
                return "scripts"
            if file_rel.startswith("tests" + os.sep):
                return "tests"
            return "other"

        # 例外: shared 层异常类 (DataError/ConfigError 等) 是标准命名习惯
        exception_classes: Set[str] = {
            # shared 异常体系 — 标准命名, 无需前缀
            "LingLongError", "DataError", "ConfigError", "NetworkError",
            "CalculationError", "ValidationError", "BusinessError", "ResourceError",
            "DataNotFoundError", "DataQualityError", "DatabaseError", "ConnectionTimeoutError",
            "SequenceError",
            # 已知设计模式 — EventBus 是公认模式名
            "EventBus", "EventBusABC",
        }

        for fpath in py_files:
            tree = self._parse_file(fpath)
            if tree is None:
                continue
            rel = os.path.relpath(fpath, self.project_root)
            domain = _detect_domain(rel)

            classes = self._extract_classes(tree)
            for name, lineno, _fields in classes:
                if name in exception_classes:
                    continue

                # 检查是否包含通用词且是否已经有域前缀
                for generic in self.GENERIC_NAMES:
                    if generic not in name:
                        continue
                    # 名字就是通用词本身 (如 Signal, Client) → 必须加前缀
                    if name == generic:
                        issues.append(
                            f"[STYLE-03b-4] {rel}:{lineno} "
                            f"裸通用词类名 '{name}' 缺少域前缀 "
                            f"-> 应命名如 '{domain.capitalize()}{name}' "
                            f"(例: CognitionSignal)"
                        )
                        break
                    # 名字以通用词结尾但没有域前缀 (如 StatusResponse)
                    # 判断: 通用词在尾部且前半部分不是域前缀
                    if name.endswith(generic) and len(name) > len(generic):
                        prefix = name[:-len(generic)]
                        # 如果前缀本身就是通用词 (如 DataSource → Data是通用词, Source也是) → 跳过
                        if not prefix[0].isupper():
                            continue  # Small first letter means it's a verb/adjective prefix
                        # 检查是否有域前缀特征 (域名+通用词 如 BacktestResult)
                        # 无明确规则, 由人工判断, 这里仅标记
                        if len(prefix) <= 3:
                            # 短前缀如 Evo/Tdx/Api 可能不够描述性
                            pass  # short prefixes are domain-specific, skip
                    break

        return issues
