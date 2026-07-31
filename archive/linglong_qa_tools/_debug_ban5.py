"""直接debug：为什么0和1还在报错"""
from shared._path_config import (
    TDX_BASE, TDX_VIPDOC, TDX_PYPLUGINS, TDX_PYPLUGINS_DATA,
    MARKET_DB, FUNDAMENTALS_DB, PROJECT_ROOT,
    SYNOLOGY_ROOT, TRADE_RUNTIME, TRADE_TDX, SPB_DATA,
    get_tdx_vipdoc, get_tdx_sentiment_js, get_tdx_miscinfo_jso,
)
import os
import sys
import ast

QA_ROOT = r"E:\WB\qa-system"
sys.path.insert(0, os.path.join(QA_ROOT, "scripts"))

from chk_codebanchecker import CodeBanChecker
from chk_load_yaml import load_yaml

CONFIG_PATH = os.path.join(QA_ROOT, ".ai", "projects", "linglong_local.yaml")
cfg = load_yaml(CONFIG_PATH)
code_ban_cfg = cfg.get('code_ban_check', {})

checker = CodeBanChecker(code_ban_cfg, str(PROJECT_ROOT))

print(f"magic_whitelist: {sorted(checker.magic_whitelist)[:20]}...")
print(f"0 in whitelist: {0 in checker.magic_whitelist}")
print(f"0.0 in whitelist: {0.0 in checker.magic_whitelist}")
print(f"1 in whitelist: {1 in checker.magic_whitelist}")

# 直接测试 llm_tracker.py
test_file = r"E:\WB\linglong\domain\access\llm_tracker.py"
tree = checker._parse_ast(test_file)
checker._annotate_parents(tree)

issues = checker._check_magic_numbers([test_file])
print(f"\nllm_tracker.py issues: {len(issues)}")
for i in issues[:10]:
    print(f"  {i[:100]}")

# 手动看第25行的节点
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        parent = getattr(node, 'parent', None)
        grandparent = getattr(parent, 'parent', None) if parent else None
        if node.lineno in [25, 26, 43, 48, 50]:
            print(f"\n  line {node.lineno}: val={node.value}, type={type(node.value).__name__}")
            print(f"    parent: {type(parent).__name__ if parent else None}")
            print(f"    in whitelist: {node.value in checker.magic_whitelist}")
            print(f"    is AnnAssign: {isinstance(parent, ast.AnnAssign) if parent else False}")
