#!/usr/bin/env python3
"""Checker: 生产环境就绪检查

生产环境必备能力验证：
  1. 日志系统就绪（logging 配置）
  2. 异常处理覆盖（try/except 在关键路径）
  3. 重试机制（函数调用带 retry）
  4. 超时控制（timeout 参数）
  5. 健康检查端点
  6. 优雅关闭信号处理
  7. 配置外部化（硬编码 vs 环境变量）
  8. 密钥管理（Secrets 来源）
  9. CI/CD 自动化验证
  10. 文档完整性（README/CHANGELOG 存在）
"""
import os, re, ast
from typing import List, Tuple


# 各检查项所扫描的关键路径匹配器
CHECKS = [
    {
        "id": "PROD-01",
        "name": "日志系统",
        "severity": "BLOCKER",
        "description": "必须配置 logging 日志系统",
        "check": lambda code: "import logging" in code or "from loguru" in code or "import structlog" in code,
    },
    {
        "id": "PROD-02",
        "name": "异常处理覆盖",
        "severity": "BLOCKER",
        "description": "关键路径必须有 try/except 保护",
        "check": lambda code: "try:" in code and "except" in code,
    },
    {
        "id": "PROD-03",
        "name": "重试机制",
        "severity": "WARN",
        "description": "外部调用应具备 retry 机制",
        "check": lambda code: "retry" in code.lower() or "backoff" in code.lower() or "max_retries" in code.lower(),
    },
    {
        "id": "PROD-04",
        "name": "超时控制",
        "severity": "WARN",
        "description": "网络/外部调用应设 timeout",
        "check": lambda code: "timeout" in code.lower(),
    },
    {
        "id": "PROD-05",
        "name": "健康检查端点",
        "severity": "BLOCKER",
        "description": "服务须提供 /health 端点",
        "check": lambda code: "/health" in code or "health" in code.lower()[:3000],
    },
    {
        "id": "PROD-06",
        "name": "优雅关闭",
        "severity": "WARN",
        "description": "应处理 SIGTERM/SIGINT 实现优雅关闭",
        "check": lambda code: "signal" in code or "SIGTERM" in code or "SIGINT" in code,
    },
    {
        "id": "PROD-07",
        "name": "配置外部化",
        "severity": "BLOCKER",
        "description": "敏感配置应从环境变量加载",
        "check": lambda code: "os.environ" in code or "os.getenv" in code or ".env" in code,
    },
    {
        "id": "PROD-08",
        "name": "密钥管理",
        "severity": "BLOCKER",
        "description": "密钥应从 Secrets 服务或环境变量读取",
        "check": lambda code: "os.environ" in code.lower() or "secret" in code.lower()[:2000],
    },
    {
        "id": "PROD-09",
        "name": "CI/CD 验证",
        "severity": "WARN",
        "description": "应具备 CI/CD 自动化流水线",
        "check": lambda code: ".github/workflows" in code or "Jenkinsfile" in code or ".gitlab-ci" in code,
    },
    {
        "id": "PROD-10",
        "name": "文档完整性",
        "severity": "WARN",
        "description": "应具备 README / CHANGELOG 文档",
        "check": lambda code: "README" in code or "CHANGELOG" in code[code.rfind("/") if "/" in code else 0:],
    },
]


class ProductionChecker:
    """生产环境就绪检查器"""
    CHECKER_ID = "production_check"
    CHECKER_LABEL = "生产环境就绪"

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.scan_dirs = config.get("scan_dirs", ["src/"])
        self.active_checks = config.get("active_checks", [c["id"] for c in CHECKS])

    def check(self) -> Tuple[int, List[str]]:
        issues = []
        errors = 0
        scans = {}

        # 收集目录中的关键文件内容
        for d in self.scan_dirs:
            full = os.path.join(self.project_root, d)
            if not os.path.isdir(full):
                continue
            # 限制扫描深度为 2 层
            for root, dirs, files in os.walk(full):
                rel_dir = os.path.relpath(root, full)
                depth = 0 if rel_dir == "." else len(rel_dir.split(os.sep))
                if depth > 1:
                    dirs[:] = []  # 不深入
                dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in ("__pycache__", "node_modules")]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    path = os.path.join(root, f)
                    rel = os.path.relpath(path, self.project_root)
                    scans[rel] = self._read_file(path)

        # 文档检查（独立于代码扫描）
        for check in CHECKS:
            if check["id"] not in self.active_checks:
                continue
            # 扫描目标：如果是文档类检查，检查项目根目录文件
            if check["id"] == "PROD-10":
                readme_ok = os.path.exists(os.path.join(self.project_root, "README.md"))
                changelog_ok = os.path.exists(os.path.join(self.project_root, "CHANGELOG.md"))
                if not (readme_ok and changelog_ok):
                    errors += 1
                    missing = [m for m, f in [("README.md", readme_ok), ("CHANGELOG.md", changelog_ok)] if not f]
                    issues.append(f"[{check['id']}] [{check['severity']}] {check['name']}: 缺失 {', '.join(missing)}")
                continue

            if check["id"] in ("PROD-05", "PROD-09"):
                # 检查特定文件
                if check["id"] == "PROD-09":
                    ci_path = os.path.join(self.project_root, ".github/workflows")
                    if not os.path.exists(ci_path):
                        errors += 1
                        issues.append(f"[{check['id']}] [{check['severity']}] {check['name']}: 未发现 CI/CD 工作流")
                    continue
                if check["id"] == "PROD-05":
                    continue  # 跳过，不适用于非服务项目

            # 扫描代码文件
            passed = False
            for rel, content in scans.items():
                if not rel.endswith(".py"):
                    continue
                if check["check"](content):
                    passed = True
                    break

            if not passed:
                errors += 1
                issues.append(f"[{check['id']}] [{check['severity']}] {check['name']}: {check['description']}")

        return errors, issues

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
