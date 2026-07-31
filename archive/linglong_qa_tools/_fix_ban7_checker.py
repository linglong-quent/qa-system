"""修复 BAN-7 checker：排除 docstring 中的 IP"""

QA_FILE = r"E:\WB\qa-system\scripts\chk_codebanchecker.py"

with open(QA_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    def _check_hardcoded_ip(self, py_files: List[str]) -> List[str]:
        issues = []
        IP_PATTERN = re.compile(r"\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b")
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
        return issues'''

new = '''    def _collect_docstring_nodes(self, tree: ast.AST) -> set:
        """收集所有 docstring 节点（模块、类、函数的文档字符串）"""
        doc_nodes = set()
        # 模块 docstring
        mod_doc = ast.get_docstring(tree)
        if mod_doc:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value == mod_doc:
                        doc_nodes.add(node)
                        break
        # 类和函数的 docstring
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
                            doc_nodes.add(child.value)
                            break
        return doc_nodes

    def _check_hardcoded_ip(self, py_files: List[str]) -> List[str]:
        issues = []
        IP_PATTERN = re.compile(r"\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b")
        for fpath in py_files:
            tree = self._parse_ast(fpath)
            if tree is None:
                continue
            doc_nodes = self._collect_docstring_nodes(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                # 排除 docstring
                if node in doc_nodes:
                    continue
                ips = IP_PATTERN.findall(node.value)
                for ip in ips:
                    if ip not in ("0.0.0.0", "127.0.0.1", "255.255.255.255"):
                        issues.append(
                            f"[BAN-7] {fpath}:{node.lineno} 硬编码 IP '{ip}' -> " f"应从配置文件读取，参考 CWE-200"
                        )
        return issues'''

if old in content:
    content = content.replace(old, new)
    with open(QA_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ BAN-7 checker 已修复（排除 docstring）")
else:
    print("✗ 没找到旧代码")
    # 看看现有的
    if '_collect_docstring_nodes' in content:
        print("  (docstring 排除已存在)")
    else:
        # 打印一下当前的 _check_hardcoded_ip
        import re
        m = re.search(r'def _check_hardcoded_ip\(self.*?return issues', content, re.DOTALL)
        if m:
            print("当前函数:")
            print(m.group(0)[:500])
