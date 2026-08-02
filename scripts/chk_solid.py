#!/usr/bin/env python3
"""Checker: SOLID 五原则静态门禁 (AST)

将 SOLID 设计原则做成 QA 可执行的机器检查:

  S 单一职责  — 函数体过长 / 参数过多 (上帝函数)
  O 开闭原则  — 模块内同构函数体重复 (复制粘贴实现, 扩展需改多处)
  L 里氏替换  — 子类覆写父类方法但签名参数个数严重不兼容
  I 接口隔离  — 类方法过多 (上帝类) / 实例方法参数过多
  D 依赖倒置  — domain 模块跨域直连具体实现 (非 domain/<域>/api/ 抽象层)

D 原则语义 (v2): 依据架构宪法「跨域调用必须走 domain/*/api/」,
对 domain/ 下每个模块检查其 import 是否直连其他域的具现实现
(非 api 层、非白名单)。scripts 应用层依赖 domain 属正常分层, 不判违规。

统一接口: check() -> (errors: int, issues: List[str])
配置示例 (projects/*.yaml 或 review-rules.yaml):
  solid_check:
    enabled: true
    scan_dirs: ["domain/", "scripts/", "shared/"]
    severity: WARN                # BLOCKER | WARN | INFO (Gate5 据此决定是否阻断)
    func_max_lines: 120           # S: 函数体行数阈值
    func_max_args: 7              # S: 函数参数个数阈值 (排除 self/cls)
    class_max_methods: 16         # I: 类方法数阈值 (上帝类)
    method_max_args: 8            # I: 实例方法参数阈值 (含 self, 排除 __init__)
    override_arg_tolerance: 3     # L: 覆写签名参数个数容忍度
    dup_body_min_lines: 12        # O: 判定重复的最小函数体行数
    allowed_concrete: []          # D: 白名单 (允许跨域直连的具现, 形如 domain.data.theme.follow_degree)
"""
import ast
import os
from collections import defaultdict
from typing import Dict, List, Tuple


class SolidChecker:
    """SOLID 五原则检查器

    统一接口: check() -> (errors, issues)
    """

    DEFAULTS = {
        "func_max_lines": 120,
        "func_max_args": 7,
        "class_max_methods": 16,
        "method_max_args": 8,
        "override_arg_tolerance": 3,
        "dup_body_min_lines": 12,
        "allowed_concrete": [],
    }

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        cfg = dict(self.DEFAULTS)
        cfg.update(config or {})
        self.scan_dirs = cfg.get("scan_dirs", ["domain/", "scripts/", "shared/"])
        self.func_max_lines = int(cfg.get("func_max_lines"))
        self.func_max_args = int(cfg.get("func_max_args"))
        self.class_max_methods = int(cfg.get("class_max_methods"))
        self.method_max_args = int(cfg.get("method_max_args"))
        self.override_arg_tolerance = int(cfg.get("override_arg_tolerance"))
        self.dup_body_min_lines = int(cfg.get("dup_body_min_lines"))
        self.allowed_concrete = set(cfg.get("allowed_concrete", []))
        # 第一遍收集的类→方法签名映射 (供 L 检查)
        self._class_methods: Dict[str, Dict[str, int]] = {}

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        errors = 0
        py_files = self._collect_py_files()
        # 第一遍: 收集类结构 (L 需要全量映射)
        for fpath in py_files:
            tree = self._parse(fpath)
            if tree is None:
                continue
            self._collect_class_methods(tree)
        # 第二遍: 逐文件五原则检查
        for fpath in py_files:
            tree = self._parse(fpath)
            if tree is None:
                continue
            rel = os.path.relpath(fpath, self.project_root)
            e, iss = self._check_file(fpath, rel, tree)
            errors += e
            issues.extend(iss)
        return errors, issues

    # ── 收集 ────────────────────────────────────────────────

    def _collect_py_files(self) -> List[str]:
        files = []
        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, dirs, names in os.walk(full):
                dirs[:] = [x for x in dirs if not x.startswith(".")
                           and x not in ("__pycache__", "node_modules")]
                for n in names:
                    if n.endswith(".py") and n != "__init__.py":
                        files.append(os.path.join(root, n))
        return files

    @staticmethod
    def _parse(fpath: str):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return ast.parse(f.read())
        except (SyntaxError, UnicodeDecodeError, OSError):
            return None

    def _collect_class_methods(self, tree: ast.AST) -> None:
        """第一遍: 收集 类名 → {方法名: 参数个数(含 self/cls)}."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = {}
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nargs = len(item.args.args) if item.args.args else 0
                        methods[item.name] = nargs
                if methods:
                    self._class_methods.setdefault(node.name, methods)

    # ── 五原则检查 ──────────────────────────────────────────

    def _check_file(self, fpath: str, rel: str, tree: ast.AST) -> Tuple[int, List[str]]:
        errors = 0
        issues: List[str] = []
        cur_domain = self._file_domain(rel)

        # O: 模块内同构函数体重复 (先归一化收集)
        body_groups: Dict[str, List[ast.FunctionDef]] = defaultdict(list)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body_lines = (node.end_lineno or node.lineno) - node.lineno
                # S1: 函数体过长
                if body_lines > self.func_max_lines:
                    errors += 1
                    issues.append(
                        f"[SOLID-S] {rel}:{node.lineno} 函数 {node.name} 体 "
                        f"{body_lines} 行 > {self.func_max_lines} (单一职责)"
                    )
                # S2: 参数过多
                nargs = len(node.args.args) if node.args.args else 0
                if nargs > self.func_max_args:
                    errors += 1
                    issues.append(
                        f"[SOLID-S] {rel}:{node.lineno} 函数 {node.name} 参数 "
                        f"{nargs} 个 > {self.func_max_args} (单一职责)"
                    )
                # O: 函数体 >= 阈值 且非单行, 记入归一化分组
                if body_lines >= self.dup_body_min_lines:
                    sig = ast.dump(node, include_attributes=False)
                    sig = sig.split("lineno=")[0]
                    body_groups[sig].append(node)

            elif isinstance(node, ast.ClassDef):
                # I1: 上帝类
                methods = [m for m in node.body
                           if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if len(methods) > self.class_max_methods:
                    errors += 1
                    issues.append(
                        f"[SOLID-I] {rel}:{node.lineno} 类 {node.name} 方法 "
                        f"{len(methods)} 个 > {self.class_max_methods} (接口隔离/上帝类)"
                    )
                # I2: 方法参数过多 (排除 __init__)
                for m in methods:
                    if m.name == "__init__":
                        continue
                    nargs = len(m.args.args) if m.args.args else 0
                    if nargs > self.method_max_args:
                        errors += 1
                        issues.append(
                            f"[SOLID-I] {rel}:{m.lineno} 方法 {node.name}.{m.name} 参数 "
                            f"{nargs} 个 > {self.method_max_args} (接口隔离)"
                        )
                # L: 覆写签名不兼容
                for base in node.bases:
                    base_name = getattr(base, "id", "")
                    parent = self._class_methods.get(base_name)
                    if not parent:
                        continue
                    for m in methods:
                        if m.name not in parent:
                            continue
                        cur = len(m.args.args) if m.args.args else 0
                        diff = abs(cur - parent[m.name])
                        if diff > self.override_arg_tolerance:
                            errors += 1
                            issues.append(
                                f"[SOLID-L] {rel}:{m.lineno} {node.name}.{m.name} 覆写 "
                                f"{base_name}.{m.name} 参数差 {diff} > {self.override_arg_tolerance} (里氏替换)"
                            )

        # O: 报告重复实现
        for sig, funcs in body_groups.items():
            if len(funcs) <= 1:
                continue
            names = ", ".join(f"{f.name}@L{f.lineno}" for f in funcs[:4])
            errors += 1
            issues.append(
                f"[SOLID-O] {rel} 同构函数体重复 {len(funcs)} 处: {names} "
                f"(开闭原则, 应收敛为单一实现)"
            )

        # D: domain 模块跨域直连具体实现 (AGENTS.md 宪法: 跨域必须走 domain/*/api/)
        if cur_domain:
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if self._is_cross_domain_violation(mod, cur_domain):
                        errors += 1
                        issues.append(
                            f"[SOLID-D] {rel}:{node.lineno} from '{mod}' "
                            f"跨域直连具体实现, 应经 domain.<域>.api/ 抽象 (依赖倒置)"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                        if self._is_cross_domain_violation(mod, cur_domain):
                            errors += 1
                            issues.append(
                                f"[SOLID-D] {rel}:{node.lineno} import '{mod}' "
                                f"跨域直连具体实现, 应经 domain.<域>.api/ 抽象 (依赖倒置)"
                            )

        return errors, issues

    @staticmethod
    def _file_domain(rel: str) -> str:
        """返回 rel 路径所属 domain 名 (domain/<域>/... 则返回 <域>, 否则空串)."""
        parts = rel.split(os.sep)
        if len(parts) >= 2 and parts[0] == "domain":
            return parts[1]
        return ""

    def _is_cross_domain_violation(self, mod: str, cur_domain: str) -> bool:
        """判定 domain.<其他域>.<具体实现> 是否构成跨域直连违规."""
        if mod in self.allowed_concrete:
            return False
        parts = mod.split(".")
        if len(parts) < 3:
            return False
        if parts[0] != "domain" or parts[1] == cur_domain:
            return False
        third = parts[2]
        if third == "api" or third.startswith("api"):
            return False
        return True
