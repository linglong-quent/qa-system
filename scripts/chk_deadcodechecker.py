#!/usr/bin/env python3
"""Checker: detect orphan (unreferenced) public symbols — dead code.

Rationale:
    Dead code (functions, classes, and constants that are never imported)
    increases maintenance burden, confuses readers, and can hide bugs
    (CWE-561). Every public symbol should be used by at least one import
    in the project.

References:
    - CWE-561: Dead Code
    - KUN BAN-14 / G5A-010
    - Vulture (Python dead code detector) methodology
"""

import ast
import os
import re
from typing import List, Set, Tuple


class DeadCodeChecker:
    """Detect orphan public functions, classes, and constants."""

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "scripts/", "tests/"])
        # Symbols whose names match these patterns are exempt
        self.exempt_names = config.get("exempt_names", [
            "main", "__init__", "__main__", "__version__", "__all__",
            "app", "application", "router", "run",
        ])
        self.entry_points = config.get("entry_points", ["main.py", "app.py", "cli.py"])
        # DEADCODE-002：临时/调试/备份残留（文件名或所在目录名命中即报）
        self.junk_patterns = config.get("junk_patterns", [
            # 词边界（_ / 数字 / 结尾）—— 避免 `_templates`(temp+lates)、
            # `_testing` 之类被误伤
            r"^_(probe|dbg|debug|tmp|temp|scratch|bak|old|copy)(_|$|\d)",
            r"^_(check|verify|audit|fix|patch|retro|test)(_|$|\d)",
            r"^_\w+_backup(_|$|\d)",
            r"^\w+_old\d*$", r"^\w+_bak\d*$", r"^\w+_copy\d*$",
            r"^untitled\d*$", r"^new_?file\d*$",
            r"^tmp_\w+", r"^temp_\w+",
        ])
        # DEADCODE-003 只对库目录生效：scripts/ tools/ ci/ ops/ 下的文件由 CLI/调度器
        # 直接执行，本就不该被 import，对其报"孤岛模块"是纯噪声（实测 1036 条）。
        self.library_dirs = config.get("library_dirs", [
            "src/", "domain/", "shared/", "core/", "app/", "lib/",
        ])
        self.junk_dirs = config.get("junk_dirs", [
            "_recovery_backup", "_backup", "backups", "_bak", "_old",
            "_deprecated", "_tmp", ".tmp", "_scratch", "_trash", "_to_delete",
        ])

    def _collect_py_files(self, dirs: List[str]) -> List[str]:
        """收集 .py 文件。

        排除规则（接多仓后必需，否则 .venv/node_modules 会被全量扫入）：
        - 硬编码 skip 目录名
        - 配置的 exclude_patterns（glob 归一为路径片段）
        """
        skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "backups",
                "site-packages", "build", "dist", "_deprecated", "archive", "_archive",
                "old_versions", "scripts_backup", "backup", "_backup"}
        frags = []
        for pat in (self.config.get("exclude_patterns", []) or []):
            p = str(pat).replace("\\", "/").strip().strip("*").strip("/")
            p = p.replace("**", "").strip("/")
            if p:
                frags.append(p)

        files = []
        for d in dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            for root, subdirs, fnames in os.walk(full):
                subdirs[:] = [
                    s for s in subdirs
                    if s not in skip
                    and not any(f in os.path.join(root, s).replace("\\", "/")
                                for f in frags)
                ]
                for fn in fnames:
                    if not fn.endswith(".py"):
                        continue
                    fp_ = os.path.join(root, fn)
                    if any(f in fp_.replace("\\", "/") for f in frags):
                        continue
                    files.append(fp_)
        return files

    def _extract_public_symbols(self, tree: ast.AST) -> List[str]:
        """模块顶层的公共 API 面：函数 / 类 / 常量。

        只看 ``tree.body``（模块顶层），不再 ast.walk 整棵树 —— 原实现会把
        类方法（``def trade_value(self)``）和函数体内的局部赋值都当"公共符号"，
        对 linglong 实测产生 5462 条噪声（占全部报点 96%）。

        类方法"未被引用"是弱信号（可能是接口实现 / 插件钩子 / 动态调用），
        不属于 DEADCODE-001 的判定范围。
        """
        symbols = []
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith("_"):
                    continue
                # 带装饰器的符号 = 框架注册模式(路由/任务/事件处理器/定时器),
                # 运行时按 URL/调度器注册表调用, AST 无 import 引用 → 非孤儿
                if node.decorator_list:
                    continue
                symbols.append(node.name)
            elif isinstance(node, ast.Assign):
                # 仅模块顶层常量
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        symbols.append(target.id)
        return symbols

    def _extract_used_names(self, py_files: List[str]) -> Set[str]:
        """Extract every referenced name across all files.

        收集范围比"仅 import"更宽, 以消除常见误报:
        - import / from-import 的名字
        - 模块内自用 (ast.Name 与 ast.Attribute.attr, 如 ``self.RECORDS.append``)
        - importlib 字符串模块路径 (api 镜像层 ``_IMPORTS``, ``import_module("a.b.c")``)
        """
        used: Set[str] = set()
        _DOTTED = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
        for fpath in py_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        used.add(alias.name)
                        for seg in alias.name.split("."):
                            used.add(seg)
                elif isinstance(node, ast.ImportFrom):
                    # 模块路径本身也是引用：`from a.b.c import X` 必须把
                    # `a.b.c` 计入，否则 a/b/c.py 会被误判为孤岛模块。
                    if node.module:
                        used.add(node.module)
                        for seg in node.module.split("."):
                            used.add(seg)
                    for alias in node.names:
                        used.add(alias.asname or alias.name)
                elif isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
                elif isinstance(node, ast.Assign):
                    # __all__ = ["a", "b"] → 显式公开 API, 视为被引用
                    for target in node.targets:
                        if (isinstance(target, ast.Name) and target.id == "__all__"
                                and isinstance(node.value, (ast.List, ast.Tuple))):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    used.add(elt.value)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # 点分模块路径的末段: "domain.data.news_event_cache" -> news_event_cache
                    if _DOTTED.match(node.value):
                        used.add(node.value.rsplit(".", 1)[-1])
        return used

    def _file_level(self, py_files: List[str], all_used: Set[str]) -> List[str]:
        """文件级死代码/问题代码判定（原 checker 完全缺失这一层）。"""
        out: List[str] = []
        junk_re = [re.compile(p, re.I) for p in self.junk_patterns]
        for fpath in py_files:
            rel = os.path.relpath(fpath, self.project_root).replace("\\", "/")
            parts = rel.split("/")
            base = parts[-1]
            stem = base[:-3] if base.endswith(".py") else base

            # DEADCODE-002 临时/调试/备份残留
            hit_dir = next((d for d in parts[:-1] if d in self.junk_dirs), None)
            hit_name = next((p.pattern for p in junk_re if p.match(stem)), None)
            if hit_dir:
                out.append(
                    f"[DEADCODE-002] {rel} 位于残留目录 '{hit_dir}/' "
                    f"-> 临时/备份代码不应留在受版本控制的源码树，请删除或移出")
                continue
            if hit_name:
                out.append(
                    f"[DEADCODE-002] {rel} 文件名疑似临时/调试/备份残留 "
                    f"(匹配 {hit_name}) -> 确认无用后应删除，勿留在生产源码树")
                continue

            # DEADCODE-003 孤岛模块：无任何文件 import 其模块路径，且非入口脚本
            if base in ("__init__.py",) or base in self.entry_points:
                continue
            abs_norm = fpath.replace("\\", "/")
            in_lib = any(
                rel.startswith(d) or ("/" + d.strip("/") + "/") in abs_norm
                for d in self.library_dirs
            )
            if not in_lib:
                continue          # 脚本目录：直接执行，不适用"孤岛模块"判定
            mod = rel[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            short = mod.rsplit(".", 1)[-1]
            imported = any(
                u == mod or u == short or mod.endswith("." + u)
                for u in all_used if isinstance(u, str)
            )
            # 目录级 __init__ 导出 / 字符串动态引用也视为被引用
            if not imported and short not in all_used:
                out.append(
                    f"[DEADCODE-003] {rel} 孤岛模块：无任何文件 import '{mod}' "
                    f"-> 未被引用的模块是死代码，确认无用后应删除或归档")
        return out

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        py_files = self._collect_py_files(self.scan_dirs)

        # 引用收集范围 = 业务扫描目录 + ref_dirs (默认 scripts/ + tests/)
        # 业务公共符号可能仅被测试或运维脚本引用, 扫描范围过窄会产生大量误报
        extra_ref_dirs = self.config.get("ref_dirs", ["scripts", "tests"])
        ref_dirs = list(dict.fromkeys(self.scan_dirs + extra_ref_dirs))
        ref_files = self._collect_py_files(ref_dirs)
        all_used = self._extract_used_names(ref_files)

        # Track global-used names from entry points
        entry_point_imports: Set[str] = set()
        for ep in self.entry_points:
            ep_path = os.path.join(self.project_root, ep)
            if os.path.isfile(ep_path):
                try:
                    with open(ep_path, "r", encoding="utf-8") as f:
                        ep_tree = ast.parse(f.read(), filename=ep_path)
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for node in ast.walk(ep_tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            entry_point_imports.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            entry_point_imports.add(alias.asname or alias.name)

        all_used |= entry_point_imports

        # ── DEADCODE-002/003：文件级判定 ──────────────────────
        issues.extend(self._file_level(py_files, all_used))

        # Check each file for orphan public symbols
        for fpath in py_files:
            rel = os.path.relpath(fpath, self.project_root)
            # Skip entry points themselves
            if os.path.basename(fpath) in self.entry_points:
                continue
            # Skip __init__.py — they are implicit entry points
            if os.path.basename(fpath) == "__init__.py":
                continue

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, UnicodeDecodeError):
                continue

            symbols = self._extract_public_symbols(tree)
            for sym in symbols:
                if sym in self.exempt_names:
                    continue
                # Check if this symbol is referenced anywhere in the project
                # (import / 模块内自用 / 属性访问 / 字符串模块路径)
                if sym not in all_used:
                    issues.append(
                        f"[DEADCODE-001] {rel} 公共符号 '{sym}' 未被项目引用 "
                        f"-> 孤儿代码增加维护成本，确认无用后应删除或归档"
                    )

        return len(issues), issues
