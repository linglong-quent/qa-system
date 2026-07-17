from typing import List
from chk_codeban_a import CodeBanBase


class CodeBanMid(CodeBanBase):
    def _contains_sql_keyword(self, text: str) -> bool:
        """检查字符串是否包含 SQL 关键词"""
        upper = text.upper()
        return any(kw in upper for kw in self.SQL_KEYWORDS)

    # ─── 规则 3: except: pass 吞异常 ───

    def _check_except_pass(self, py_files: List[str]) -> List[str]:
        """检测 except: pass 或 except Exception: pass 吞异常"""
        import ast as ast_module

        issues = []
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast_module.walk(tree):
                if not isinstance(node, ast_module.ExceptHandler):
                    continue
                # 检查 except 块体是否只有 pass
                body = node.body
                if len(body) == 1 and isinstance(body[0], ast_module.Pass):
                    exc_type = ""
                    if node.type:
                        if isinstance(node.type, ast_module.Name):
                            exc_type = f" {node.type.id}"
                        elif isinstance(node.type, ast_module.Tuple):
                            names = [e.id for e in node.type.elts if isinstance(e, ast_module.Name)]
                            exc_type = f" {', '.join(names)}"
                    issues.append(
                        f"[BAN-3] {fpath}:{node.lineno} except{exc_type}: pass 吞异常 -> "
                        f"应至少记录日志 logger.exception() 或 re-raise"
                    )
                # 检查 except 块体只有 logging.debug() （过轻处理）
                elif (
                    len(body) == 1
                    and isinstance(body[0], ast_module.Expr)
                    and isinstance(body[0].value, ast_module.Call)
                ):
                    call = body[0].value
                    func = call.func
                    if (
                        isinstance(func, ast_module.Attribute)
                        and isinstance(func.value, ast_module.Name)
                        and func.value.id == "logging"
                        and func.attr in ("debug",)
                    ):
                        issues.append(
                            f"[BAN-3] {fpath}:{node.lineno} except: 仅 logging.debug() 吞异常 -> "
                            f"应升级为 logger.exception() 或 re-raise"
                        )
        return issues

    # ─── 规则 4: 跨层直连 ───

    def _check_cross_layer(self, py_files: List[str]) -> List[str]:
        """检测跨层 import（如 P0 直调 P3）"""
        import ast as ast_module

        issues = []
        # 构建模块到层级的映射
        module_to_layer = {}
        for layer_name, dirs in self.layers.items():
            for d in dirs:
                module_to_layer[d.rstrip("/").split("/")[-1]] = layer_name

        for fpath in py_files:
            # 确定当前文件所属层级
            current_layer = None
            for layer_name, dirs in self.layers.items():
                if any(fpath.startswith(d) for d in dirs):
                    current_layer = layer_name
                    break
            if current_layer is None:
                continue

            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast_module.walk(tree):
                if not isinstance(node, ast_module.ImportFrom):
                    continue
                if node.module is None:
                    continue
                # 检查 import 的模块是否属于其他层级
                imported_module = node.module.split(".")[0]
                target_layer = module_to_layer.get(imported_module)
                if target_layer and target_layer != current_layer:
                    issues.append(
                        f"[BAN-4] {fpath}:{node.lineno} 跨层直连: "
                        f"{current_layer} 层 import {target_layer} 层 ({node.module}) -> "
                        f"应通过接口层/事件总线间接调用"
                    )
        return issues

    def _check_core_import_boundary(self, py_files: List[str]) -> List[str]:
        """检测 _core/ 是否 import 外部目录（依赖方向铁律）

        _core/ 只能 import:
          - Python 标准库
          - _core/ 自身模块
          - 外部 pip 包
        不得 import:
          - src/ 下除 _core/ 外的其他模块
          - scripts/
          - .ai/
          - tests/
        """
        if not self.core_dirs:
            return []
        issues = []
        # 外部目录前缀（禁止 import 的目标）
        forbidden_prefixes = ["src/trading", "src/", "scripts", ".ai", "tests"]

        for fpath in py_files:
            # 仅检查 _core/ 目录下的文件
            if not any(fpath.startswith(d) for d in self.core_dirs):
                continue
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                        for pref in forbidden_prefixes:
                            if mod == pref or mod.startswith(pref + "."):
                                issues.append(
                                    f"[BAN-4a] {fpath}:{node.lineno} _core/ 禁止 import `{mod}` "
                                    f"（依赖方向铁律：_core/ 不得引用外部模块）"
                                )
                                break
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for pref in forbidden_prefixes:
                        if mod == pref or mod.startswith(pref + "."):
                            issues.append(
                                f"[BAN-4a] {fpath}:{node.lineno} _core/ 禁止 import `{mod}` "
                                f"（依赖方向铁律：_core/ 不得引用外部模块）"
                            )
                            break
        return issues

    # ─── 规则 5a: 硬编码路径 ───

    def _check_hardcoded_path(self, py_files: List[str]) -> List[str]:
        """检测硬编码文件路径"""
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
                if not isinstance(node.value, str):
                    continue
                val = node.value
                # 检测硬编码路径前缀
                if any(val.startswith(p) or val.startswith(p.replace("\\", "/")) for p in self.path_prefixes):
                    if self._is_in_main_block(node):
                        continue
                    issues.append(
                        f"[BAN-5] {fpath}:{node.lineno} 硬编码路径 '{val[:40]}' -> "
                        f"应用配置文件或环境变量 (os.path.join / pathlib)"
                    )
        return issues

    # ─── 规则 5b: 魔法数字 ───

    def _check_magic_numbers(self, py_files: List[str]) -> List[str]:
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
        return issues

    # ─── 规则 6: 修改 _core/ 接口签名 ───

    def _check_core_signature(self, changed_files: list) -> List[str]:
        """检测 _core/ 目录下函数签名变更"""
        if not changed_files:
            return []
        issues = []
        # 筛选 _core/ 下的变更文件
        core_files = [f for f in changed_files if f.endswith(".py") and any(f.startswith(d) for d in self.core_dirs)]
        if not core_files:
            return []

        # 获取 git diff 内容
        diff_content = self._get_git_diff(core_files)
        if not diff_content:
            return []

        # 检测 def 行的参数变更
        import re

        # 匹配 diff 中修改的 def 行（以 + 或 - 开头）
        added_defs = {}
        removed_defs = {}
        for line in diff_content.split("\n"):
            for prefix, store in [("+", added_defs), ("-", removed_defs)]:
                if line.startswith(prefix):
                    # 提取 def function_name(params):
                    m = re.search(r"def\s+(\w+)\s*\(([^)]*)\)", line[1:])
                    if m:
                        func_name = m.group(1)
                        params = m.group(2).strip()
                        store[func_name] = params

        # 对比签名变化
        for func_name, new_params in added_defs.items():
            if func_name in removed_defs:
                old_params = removed_defs[func_name]
                if old_params != new_params:
                    issues.append(
                        f"[BAN-6] _core/ 接口签名变更: {func_name}() "
                        f"参数从 ({old_params}) 变为 ({new_params}) -> "
                        f"_core/ 接口签名不可直接修改，应新增重载方法或废弃旧方法"
                    )
        return issues

    def _get_git_diff(self, files: list) -> str:
        """获取指定文件的 git diff"""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "HEAD", "--"] + files, capture_output=True, text=True, cwd=self.project_root
            )
            return result.stdout
        except Exception:
            return ""

    # ─── 规则 7: 硬编码 IP 地址（源自 KUN G5A-002 → OWASP/CWE-200）───
