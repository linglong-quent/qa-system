#!/usr/bin/env python3
"""Checker: 跨仓库克隆 / 文档声明↔实测基线 / 构建可复现性 / 路径外置与探活

合并四类盲区规则（T29 盲区④⑤⑥ + 追加第七类），每类可独立开关：
  CLONE-001 同源文件 MD5 全等（复制而非依赖）
  CLAIM-001 文档声明的数量与实测不符（如 CI hooks 13 vs 6）
  CLAIM-002 文档声明的制品/路径不存在
  BUILD-001/002/003 Dockerfile 断裂（COPY 源缺失 / 缺 [project] / CMD 模块不存在）
  PATH-001 硬编码绝对路径（盘符 / 归档 / 外部挂载）
  PATH-002 被依赖的关键路径不存在（探活）

接口: check() -> (errors: int, issues: list[str])
"""
import hashlib
import os
import re
from typing import Dict, List, Tuple

ABS_PATH = re.compile(r"""["']((?:[A-Za-z]:[\\/]|/mnt/|\\\\[^"']+)[^"'\n]{2,120})["']""")
DOC_PATH = re.compile(r"`([^`\n]{3,120}\.(?:md|py|json|yaml|yml|sql|csv|sh|js))`")
HOOK_ID = re.compile(r"^\s*-\s*id:\s*\S+", re.M)


def _read(path: str) -> str:
    try:
        return open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_files(root: str, exts=None):
    skip = {".git", ".venv", ".deps", "node_modules", "__pycache__", "site-packages"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if exts is None or fn.endswith(tuple(exts)):
                yield os.path.join(dirpath, fn)


class BlindSpotChecker:
    """盲区④⑤⑥ + 第七类 合并检查器（按配置分派）"""

    CHECKER_ID = "blindspot"
    CHECKER_LABEL = "克隆/声明/构建/路径"

    def __init__(self, config: dict, project_root: str):
        self.config = config or {}
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = self.config.get("scan_dirs", ["src/", "scripts/", "domain/"])

    # ── CLONE-001 / CLONE-002 ─────────────────────────────────
    def _clone(self) -> List[str]:
        out = []
        for pair in self.config.get("clone_pairs", []) or []:
            copy = os.path.join(self.project_root, pair["copy"].replace("/", os.sep))
            origin = pair["origin"]
            if not os.path.isabs(origin):
                origin = os.path.abspath(os.path.join(self.project_root, origin))
            if not (os.path.isdir(copy) and os.path.isdir(origin)):
                continue
            min_ratio = float(pair.get("min_equal_ratio", 0.9))
            min_files = int(pair.get("min_files", 20))
            same = diff = only = 0
            samples = []
            drift_samples = []
            for f in _walk_files(copy):
                rel = os.path.relpath(f, copy)
                other = os.path.join(origin, rel)
                if not os.path.isfile(other):
                    only += 1
                    continue
                if _md5(f) == _md5(other):
                    same += 1
                    if len(samples) < 3:
                        samples.append(rel)
                else:
                    diff += 1
                    if len(drift_samples) < 3:
                        drift_samples.append(rel)
            total = same + diff + only
            if total >= min_files and same >= min_files and (same / max(total, 1)) >= min_ratio:
                out.append(
                    f"[CLONE-001] '{pair['copy']}' 与 '{origin}' 高度同源：{same}/{total} 文件"
                    f" MD5 全等（{same / max(total, 1):.0%}，阈值 {min_ratio:.0%}），"
                    f"仅 {only} 个为本仓独有，{diff} 个不同（示例 {samples}）"
                    f" -> 属复制而非依赖，双份维护必漂移")
            # CLONE-002：同名文件内容不一致 = 双副本已漂移（如 dev 与 runtime 副本）
            if drift_samples:
                out.append(
                    f"[CLONE-002] '{pair['copy']}' 与 '{origin}' 已漂移：{diff}/{total} 个同名文件"
                    f" 内容不一致（示例 {drift_samples}）-> 双副本不同步，"
                    f"修正一份不会影响另一份（只校验其中一份的门禁看不见）")
        return out

    # ── CLAIM-001 / CLAIM-002 ─────────────────────────────────
    def _claims(self) -> List[str]:
        out = []
        for claim in self.config.get("doc_claims", []) or []:
            doc = os.path.join(self.project_root, claim["doc"].replace("/", os.sep))
            if not os.path.isfile(doc):
                out.append(f"[CLAIM-002] 声明的文档不存在：{claim['doc']}")
                continue
            src = _read(doc)
            m = re.search(claim["pattern"], src)
            if not m:
                continue
            declared = int(m.group(1))
            actual_file = os.path.join(self.project_root,
                                       claim["actual_file"].replace("/", os.sep))
            if not os.path.isfile(actual_file):
                out.append(f"[CLAIM-002] CLAIM-001 的实测对象不存在：{claim['actual_file']}")
                continue
            actual = len(HOOK_ID.findall(_read(actual_file))) if claim.get("counter", "hook_id") == "hook_id" \
                else len(_read(actual_file).splitlines())
            if declared != actual:
                out.append(
                    f"[CLAIM-001] {claim['doc']} 声明 {declared} 个（{claim['label']}），"
                    f"实测 {actual} 个（{claim['actual_file']}）-> 文档声明与事实不符")
        for path in self.config.get("declared_paths", []) or []:
            full = os.path.join(self.project_root, path.replace("/", os.sep))
            if not os.path.exists(full):
                out.append(f"[CLAIM-002] 声明存在但实测缺失：{path}")
        return out

    # ── BUILD-001/002/003 ─────────────────────────────────────
    def _build(self) -> List[str]:
        out = []
        for rel in self.config.get("dockerfiles", ["Dockerfile"]) or []:
            full = os.path.join(self.project_root, rel.replace("/", os.sep))
            if not os.path.isfile(full):
                continue
            text = _read(full)
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                m = re.match(r"COPY\s+(?:--\S+\s+)*(\S+)\s+", s)
                if m and not m.group(1).startswith("--"):
                    src = m.group(1)
                    if "*" in src or "$" in src:
                        continue
                    if not os.path.exists(os.path.join(self.project_root, src)):
                        out.append(
                            f"[BUILD-001] {rel}:{i} COPY 源 '{src}' 在构建上下文中不存在 "
                            f"-> docker build 确定性失败")
                if re.search(r"pip\s+install[^\n]*-e\s+[\"']?\.", s):
                    pp = os.path.join(self.project_root, "pyproject.toml")
                    if os.path.isfile(pp) and "[project]" not in _read(pp):
                        out.append(
                            f"[BUILD-002] {rel}:{i} 使用 pip install -e .，但 pyproject.toml "
                            f"无 [project] 表 -> 安装确定性失败")
                mm = re.search(r"[\"']([\w./]+):(\w+)[\"']", s)
                if mm and re.search(r"\b(uvicorn|gunicorn|CMD|ENTRYPOINT)\b", s):
                    mod = mm.group(1).replace(".", os.sep)
                    if not any(os.path.isfile(os.path.join(self.project_root, mod + ext))
                               for ext in (".py", os.sep + "__init__.py")):
                        out.append(
                            f"[BUILD-003] {rel}:{i} 启动目标 '{mm.group(0)}' 的模块不存在 "
                            f"-> 容器启动即 ModuleNotFoundError")
        return out

    # ── PATH-001 / PATH-002 ───────────────────────────────────
    def _paths(self) -> List[str]:
        out = []
        hits: Dict[str, int] = {}
        for d in self.scan_dirs:
            base = os.path.join(self.project_root, d.rstrip("/\\"))
            if not os.path.isdir(base):
                continue
            for path in _walk_files(base, (".py", ".js", ".ts", ".yaml", ".yml", ".json")):
                src = _read(path)
                for m in ABS_PATH.finditer(src):
                    p = m.group(1)
                    if re.search(r"\\\\[?.]\\|%TEMP%|\\\\(Users|Windows)\\\\", p, re.I):
                        continue
                    hits[p] = hits.get(p, 0) + 1
        threshold = int(self.config.get("abs_path_min_hits", 3))
        hot = {p: n for p, n in hits.items() if n >= threshold}
        if hot:
            sample = sorted(hot.items(), key=lambda kv: -kv[1])[:5]
            out.append(
                f"[PATH-001] 检出 {len(hot)} 条硬编码绝对路径（出现 ≥{threshold} 次）"
                f" -> 应外置到配置/环境变量；高频样例 {sample}")
        for p in self.config.get("critical_paths", []) or []:
            if not os.path.exists(p):
                out.append(
                    f"[PATH-002] 被依赖的关键路径不存在：{p} -> 依赖方将在运行期 "
                    f"FileNotFoundError 或静默失效（构建/门禁阶段即应告警）")
        return out

    def check(self) -> Tuple[int, List[str]]:
        issues = self._clone() + self._claims() + self._build() + self._paths()
        return len(issues), issues
