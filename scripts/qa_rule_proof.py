#!/usr/bin/env python3
"""T29 规则自证：每条规则"注入已知缺陷 → 规则触发 → 撤销注入"。

纪律（队长 T29 硬要求）：
  拿不出"它曾经失败过"的证据，这条规则就不算完成。
  —— 一个从未失败过的门禁，极可能只是被旁路了。

用法:
  python scripts/qa_rule_proof.py            # 全部用例
  python scripts/qa_rule_proof.py --json out.json
退出码: 0 = 全部规则均被证明可失败；1 = 存在未能触发的规则。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from chk_semantic import SemanticTruthChecker          # noqa: E402
from chk_docstrcode import DocstringCodeChecker        # noqa: E402
from chk_runtime import RuntimeDriftChecker            # noqa: E402
from chk_vcs import VcsGovernanceChecker               # noqa: E402
from chk_blindspot import BlindSpotChecker             # noqa: E402

FIXTURES = {}
RESULTS = []


def fixture(name):
    def deco(fn):
        FIXTURES[name] = fn
        return fn
    return deco


def _write(root, rel, content):
    p = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


# ── ① 语义真实性 ──────────────────────────────────────────────

@fixture("TRUTH-001")
def _f_truth001(root):
    _write(root, "src/fake_ic.py", '''"""伪造 IC 指标块"""
import numpy as np


def main():
    results = []
    for factor in ['momentum_20', 'reversal_10', 'volatility_20']:
        results.append({
            'factor': factor,
            'valid': np.random.random() > 0.5,
            'ic_mean': np.random.uniform(-0.1, 0.1),
            'ic_std': np.random.uniform(0.05, 0.15),
            'icir': np.random.uniform(-1, 1),
        })
    return results
''')


@fixture("TRUTH-002")
def _f_truth002(root):
    _write(root, "src/storage/conn.py", '''"""空壳假成功"""


class PGWriter:
    def save_factor_value(self, code, date, values):
        # TODO: 接入 PG 后实现
        return True

    def save_combo(self, name, factors):
        # TODO 占位
        return 1
''')


@fixture("TRUTH-003")
def _f_truth003(root):
    _write(root, "src/loader.py", '''"""静默降级"""
import pandas as pd


def load(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
''')


# ── 追加类：docstring 代码 / 未绑定名 / 改名完整性 ──────────────

@fixture("DOCSTR-001")
def _f_docstr001(root):
    # 复现 T28 P0：import/赋值被插进 docstring 内部（开三引号之后）
    # 注意：docstring 文本必须"能被当作 Python 解析"才会被判为可执行代码，
    # 真实文件里紧随其后的是 `优化版IC/IR批量计算` 这类可解析行。
    _write(root, "src/mining/stage1.py", '"""\n'
           'import logging  # noqa: E402  # print->logging migration\n'
           'logger = logging.getLogger(__name__)\n'
           'stage1/因子挖掘\n'
           '"""\n'
           'import os\n\n\n'
           'def run():\n'
           '    logger.info("start")\n'
           '    return os.getcwd()\n')


@fixture("DOCSTR-002")
def _f_docstr002(root):
    # 标记存在、但死名已被别处绑定（只报 advisory，不误报 BLOCKER）
    _write(root, "src/ok.py", '"""\n'
           'import logging  # print->logging migration\n'
           'logger = logging.getLogger(__name__)\n'
           '说明\n'
           '"""\n'
           'import logging\n'
           'logger = logging.getLogger(__name__)\n\n\n'
           'def run():\n'
           '    logger.info("ok")\n')


@fixture("UNBOUND-001")
def _f_unbound001(root):
    _write(root, "src/broken.py",
           '"""未绑定名"""\n\n\n'
           'def run():\n'
           '    return helper()\n\n\n'
           'def other():\n'
           '    return 1\n')


@fixture("RENAME-001")
def _f_rename001(root):
    # 复现 T28：改名改了使用处，没改绑定
    _write(root, "src/stage3.py", '''"""改名手术不完整"""


def run():
    df = load_factor_values()
    return factor.rank(df)          # 使用旧名


def load_factor_values():
    return {}
''')
    _write(root, "src/bindings.py", '''linglong_factor = object()
''')


# ── ③ 版本控制治理 ────────────────────────────────────────────

@fixture("VCS-001")
def _f_vcs001(root):
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, capture_output=True)
    for i in range(60):
        _write(root, f"src/m{i}.py", "x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, capture_output=True)
    for i in range(60):
        _write(root, f"src/m{i}.py", "x = 2\n")   # 100% 脏改动


@fixture("VCS-002")
def _f_vcs002(root):
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, capture_output=True)
    _write(root, "README.md", "x\n")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, capture_output=True)
    for i in range(8):
        _write(root, f"docker/f{i}.yml", "a: 1\n")   # 整目录未入库


# ── ④⑤⑥⑦ 克隆 / 声明 / 构建 / 路径 ──────────────────────────

@fixture("CLONE-001")
def _f_clone001(root):
    for i in range(25):
        body = f"VALUE = {i}\n"
        _write(root, f"src/copy/mod{i}.py", body)
        _write(root, f"../origin_domain/mod{i}.py", body)


@fixture("CLAIM-001")
def _f_claim001(root):
    _write(root, "docs/guide.md", "本仓库配置了 13 个 hooks。\n")
    _write(root, ".pre-commit-config.yaml",
           "repos:\n- repo: local\n  hooks:\n"
           "  - id: a\n  - id: b\n  - id: c\n  - id: d\n  - id: e\n  - id: f\n")


@fixture("CLAIM-002")
def _f_claim002(root):
    _write(root, "README.md", "见 docs/not_exist.md\n")


@fixture("BUILD-001")
def _f_build001(root):
    _write(root, "Dockerfile", "FROM python:3.13-slim\nCOPY .python-version .\nRUN echo ok\n")


@fixture("BUILD-002")
def _f_build002(root):
    _write(root, "Dockerfile", 'FROM python:3.13-slim\nRUN pip install --no-cache-dir -e ".[dev]"\n')
    _write(root, "pyproject.toml", "[tool.black]\nline-length = 120\n")


@fixture("BUILD-003")
def _f_build003(root):
    _write(root, "Dockerfile",
           'FROM python:3.13-slim\nCMD ["python", "-m", "uvicorn", "ops.api:app", "--port", "8000"]\n')


@fixture("PATH-001")
def _f_path001(root):
    _write(root, "src/paths.py",
           'A = os.path.join("D:", "WB", "TDX", "vipdoc", "sh", "lday")\n'
           'B = os.path.join("D:", "WB", "TDX", "vipdoc", "sh", "lday")\n'
           'C = os.path.join("D:", "WB", "TDX", "vipdoc", "sh", "lday")\n')


@fixture("PATH-002")
def _f_path002(root):
    _write(root, "src/keep.py", "x = 1\n")


@fixture("DEP-001")
def _f_dep001(root):
    for i in range(3):
        _write(root, f"src/client{i}.py", 'URL = "http://127.0.0.1:53999/api"\n')


@fixture("ID-001")
def _f_id001(root):
    _write(root, "src/collector.py", '"""伪主键"""\n'
           'import pandas as pd\n\n\n'
           'def transform(df):\n'
           '    df["news_id"] = df.index.astype(str)\n'
           '    return df\n')


@fixture("CLONE-002")
def _f_clone002(root):
    for i in range(25):
        _write(root, f"src/copy/mod{i}.py", f"VALUE = {i}\n")
        # 同名文件内容不一致 = 双副本已漂移
        _write(root, f"../origin_domain/mod{i}.py", f"VALUE = {i + 100}\n")


# ── 用例定义：rule_id → (构造器, checker, config) ──────────────

def build_cases(root):
    return [
        ("TRUTH-001", "TRUTH-001", SemanticTruthChecker,
         {"scan_dirs": ["src/"]}, _f_truth001),
        ("TRUTH-002", "TRUTH-002", SemanticTruthChecker,
         {"scan_dirs": ["src/"]}, _f_truth002),
        ("TRUTH-003", "TRUTH-003", SemanticTruthChecker,
         {"scan_dirs": ["src/"]}, _f_truth003),
        ("DOCSTR-001", "DOCSTR-001", DocstringCodeChecker,
         {"scan_dirs": ["src/"]}, _f_docstr001),
        ("DOCSTR-002", "DOCSTR-002", DocstringCodeChecker,
         {"scan_dirs": ["src/"]}, _f_docstr002),
        ("UNBOUND-001", "UNBOUND-001", DocstringCodeChecker,
         {"scan_dirs": ["src/"]}, _f_unbound001),
        ("RENAME-001", "RENAME-001", DocstringCodeChecker,
         {"scan_dirs": ["src/"], "extra_scan": ["src/bindings.py"]}, _f_rename001),
        ("VCS-001", "VCS-001", VcsGovernanceChecker,
         {"max_dirty_ratio": 0.5, "min_tracked": 10}, _f_vcs001),
        ("VCS-002", "VCS-002", VcsGovernanceChecker,
         {"critical_dirs": ["docker/"], "critical_min_files": 5}, _f_vcs002),
        ("CLONE-001", "CLONE-001", BlindSpotChecker,
         {"clone_pairs": [{"copy": "src/copy", "origin": "../origin_domain",
                           "min_equal_ratio": 0.9, "min_files": 20}]}, _f_clone001),
        ("CLAIM-001", "CLAIM-001", BlindSpotChecker,
         {"doc_claims": [{"doc": "docs/guide.md", "pattern": r"(\d+)\s*个\s*hooks",
                          "label": "hooks", "actual_file": ".pre-commit-config.yaml",
                          "counter": "hook_id"}]}, _f_claim001),
        ("CLAIM-002", "CLAIM-002", BlindSpotChecker,
         {"declared_paths": ["docs/not_exist.md"]}, _f_claim002),
        ("BUILD-001", "BUILD-001", BlindSpotChecker, {}, _f_build001),
        ("BUILD-002", "BUILD-002", BlindSpotChecker, {}, _f_build002),
        ("BUILD-003", "BUILD-003", BlindSpotChecker, {}, _f_build003),
        ("PATH-001", "PATH-001", BlindSpotChecker,
         {"scan_dirs": ["src/"], "abs_path_min_hits": 3}, _f_path001),
        ("PATH-002", "PATH-002", BlindSpotChecker,
         {"critical_paths": ["D:\\WB\\no_such_archive_dir"]}, _f_path002),
        ("DEP-001", "DEP-001", RuntimeDriftChecker,
         {"scan_dirs": ["src/"], "min_dependents": 3, "probe_endpoints": True}, _f_dep001),
        ("ID-001", "ID-001", SemanticTruthChecker,
         {"scan_dirs": ["src/"]}, _f_id001),
        ("CLONE-002", "CLONE-002", BlindSpotChecker,
         {"clone_pairs": [{"copy": "src/copy", "origin": "../origin_domain",
                           "min_equal_ratio": 0.9, "min_files": 20}]}, _f_clone002),
    ]


def run_case(rule_id, ctor, checker_cls, config, root):
    try:
        ctor(root)
        checker = checker_cls(config, root)
        errors, issues = checker.check()
        hits = [i for i in issues if f"[{rule_id}]" in i]
        return {
            "rule": rule_id,
            "injected": True,
            "errors": errors,
            "fired": len(hits) > 0,
            "sample": hits[0][:200] if hits else (issues[0][:200] if issues else ""),
            "all_issues": issues[:5],
        }
    except Exception as e:
        return {"rule": rule_id, "injected": True, "errors": -1, "fired": False,
                "sample": f"{type(e).__name__}: {e}"}


def drift_case(tmpbase):
    """DRIFT-PROC-001 需要真实进程：起一个本地 TCP 服务 → 改脚本 → 规则应报漂移"""
    import socket
    d = os.path.join(tmpbase, "driftsrv")
    os.makedirs(d, exist_ok=True)
    srv = os.path.join(d, "srv.py")
    with open(srv, "w", encoding="utf-8") as f:
        f.write("import socket, time\n"
                "s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
                "s.bind(('127.0.0.1', 53997)); s.listen(5)\n"
                "time.sleep(120)\n")
    proc = subprocess.Popen([sys.executable, srv], cwd=d,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                socket.create_connection(("127.0.0.1", 53997), timeout=0.5).close()
                break
            except Exception:
                time.sleep(0.25)
        time.sleep(1.2)
        with open(srv, "a", encoding="utf-8") as f:      # 注入：磁盘代码被改，进程未重启
            f.write("# hotfix after process start\n")
        checker = RuntimeDriftChecker({"scan_dirs": ["."], "probe_endpoints": False}, d)
        errors, issues = checker.check()
        hits = [i for i in issues if "[DRIFT-PROC-001]" in i and "53997" in i]
        return {"rule": "DRIFT-PROC-001", "injected": True, "errors": errors,
                "fired": bool(hits),
                "sample": hits[0][:250] if hits else "(未命中该端口)",
                "all_issues": issues[:5]}
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(d, ignore_errors=True)


def main():
    as_json = ""
    if "--json" in sys.argv:
        as_json = sys.argv[sys.argv.index("--json") + 1]

    print("=" * 78)
    print("  T29 规则自证 — 注入已知缺陷 → 确认规则触发 → 撤销注入")
    print("=" * 78)

    results = []
    for rule_id, expect, cls, cfg, ctor in build_cases(None):
        tmp = tempfile.mkdtemp(prefix=f"qa-proof-{rule_id}-")
        try:
            r = run_case(expect, ctor, cls, cfg, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)     # 撤销注入：删除整个 fixture
        r["fixture_removed"] = not os.path.exists(tmp)
        results.append(r)
        flag = "✅ FIRED" if r["fired"] else "❌ SILENT"
        print(f"  {flag}  {rule_id:<14} errors={r['errors']:<4} {r['sample'][:96]}")

    # DRIFT-PROC-001（需要真实进程）
    tmpbase = tempfile.mkdtemp(prefix="qa-proof-drift-")
    try:
        r = drift_case(tmpbase)
    finally:
        shutil.rmtree(tmpbase, ignore_errors=True)
    results.append(r)
    flag = "✅ FIRED" if r["fired"] else "❌ SILENT"
    print(f"  {flag}  {'DRIFT-PROC-001':<14} errors={r['errors']:<4} {r['sample'][:96]}")

    ok = sum(1 for r in results if r["fired"])
    total = len(results)
    print("-" * 78)
    print(f"  可失败证明: {ok}/{total} 规则已证明能触发")
    if ok < total:
        print("  未触发的规则: " + ", ".join(r["rule"] for r in results if not r["fired"]))
    print("=" * 78)

    if as_json:
        payload = {"total": total, "proven": ok, "cases": results}
        with open(as_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  JSON: {as_json}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
