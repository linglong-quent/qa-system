"""
给 code_ban checker 增加 IP 白名单配置支持
- BAN-7: 增加 ip_whitelist 配置项
- BAN-9: 已经有文件白名单，增加 data_config.py / *_config.py
- BAN-10: 增加 large_class_threshold 配置（默认 300，量化引擎可调到 500）
"""

checker_path = r"E:\WB\qa-system\scripts\chk_codebanchecker.py"

with open(checker_path, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# === 1. 给 _check_hardcoded_ip 增加配置化白名单 ===
old_ip_check = '''    def _check_hardcoded_ip(self, py_files: List[str]) -> List[str]:
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

new_ip_check = '''    def _check_hardcoded_ip(self, py_files: List[str]) -> List[str]:
        issues = []
        IP_PATTERN = re.compile(r"\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b")
        # 配置化 IP 白名单（配置文件中的默认值、内网测试环境等）
        ip_whitelist = set(self.config.get("ip_whitelist", []))
        ip_whitelist.update({"0.0.0.0", "127.0.0.1", "255.255.255.255"})
        # 配置文件豁免（*_config.py / config_*.py）
        config_file_patterns = self.config.get("config_file_patterns", ["_config.py", "config_"])
        for fpath in py_files:
            fname = os.path.basename(fpath)
            # 配置文件豁免
            is_config_file = any(p in fname for p in config_file_patterns)
            if is_config_file:
                continue
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
                    if ip not in ip_whitelist:
                        issues.append(
                            f"[BAN-7] {fpath}:{node.lineno} 硬编码 IP '{ip}' -> " f"应从配置文件读取，参考 CWE-200"
                        )
        return issues'''

if old_ip_check in content:
    content = content.replace(old_ip_check, new_ip_check)
    print("✓ BAN-7 已增加 ip_whitelist 和 config_file_patterns 配置")
else:
    print("✗ BAN-7 替换失败，检查匹配")

# === 2. 给 _check_bare_db_connect 增加 data_config.py 等豁免 ===
old_db_whitelist = '''    _DB_CONNECT_WHITELIST_FILES = {
        "db_conn.py", "db_config.py",       # 连接工厂
        "db_schema.py", "db_init.py",       # 建表脚本
        "migration_", "migrate_",           # 迁移脚本
        "health_check.py", "health_",       # 健康检查
        "backup.py", "backup_",             # 备份脚本
        "monitor_",                         # 监控脚本
        "evolution.py",                     # 演进脚本
    }'''

new_db_whitelist = '''    _DB_CONNECT_WHITELIST_FILES = {
        "db_conn.py", "db_config.py",       # 连接工厂
        "db_schema.py", "db_init.py",       # 建表脚本
        "migration_", "migrate_",           # 迁移脚本
        "health_check.py", "health_",       # 健康检查
        "backup.py", "backup_",             # 备份脚本
        "monitor_",                         # 监控脚本
        "evolution.py",                     # 演进脚本
        "data_config.py", "l7_health_check.py",  # 配置文件 / 运维健康检查
    }'''

if old_db_whitelist in content:
    content = content.replace(old_db_whitelist, new_db_whitelist)
    print("✓ BAN-9 已增加 data_config.py 和 l7_health_check.py 豁免")
else:
    print("✗ BAN-9 替换失败，检查匹配")

# === 3. 给 _check_large_class 增加阈值配置 ===
# 先找到当前的实现
import re
lc_match = re.search(r'def _check_large_class\(self.*?(?=\n    # ───)', content, re.DOTALL)
if lc_match:
    old_lc = lc_match.group(0)
    # 在函数开头加上阈值配置
    if "large_class_threshold" not in old_lc:
        new_lc = old_lc.replace(
            "    def _check_large_class(self, py_files: List[str]) -> List[str]:\n        issues = []\n        for fpath in py_files:",
            "    def _check_large_class(self, py_files: List[str]) -> List[str]:\n        issues = []\n        # 可配置的大阈值（量化引擎类通常偏大，可调到 500）\n        threshold = int(self.config.get(\"large_class_threshold\", 300))\n        for fpath in py_files:"
        )
        # 替换 300 为 threshold
        new_lc = new_lc.replace("> 300", f"> threshold")
        new_lc = new_lc.replace(">300", f">threshold")
        content = content.replace(old_lc, new_lc)
        print("✓ BAN-10 已增加 large_class_threshold 配置")
    else:
        print("- BAN-10 已有 large_class_threshold 配置")
else:
    print("✗ BAN-10 没找到函数")

if content != original:
    with open(checker_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✓ checker 已更新: {checker_path}")
else:
    print("\n- 无变化")
