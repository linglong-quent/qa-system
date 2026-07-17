#!/usr/bin/env python3
"""Checker: detect hardcoded secrets, passwords, tokens, and API keys.

Rationale:
    Hardcoded secrets are a critical security risk (CWE-798, OWASP Top 10).
    All credentials must be loaded from environment variables, vaults, or
    configuration files (never committed to VCS).

References:
    - CWE-798: Use of Hard-coded Credentials
    - OWASP Top 10 A03:2021 — Injection
    - KUN G5A-002 / BAN-006
"""

import os
import re
from typing import List, Tuple


class SecretChecker:
    """Scan for hardcoded secrets in source and config files."""

    # High-confidence patterns for secrets
    SECRET_PATTERNS = [
        (re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'](?!.*\$\{.*\})(?!.*<YOUR).+?["\']'), "硬编码密码"),
        (re.compile(r'(?i)(secret|api_key|apikey|api\.key)\s*[:=]\s*["\'](?!.*\$\{.*\})(?!.*<YOUR).{8,}["\']'), "硬编码密钥/API Key"),
        (re.compile(r'(?i)(token|access_token|auth_token|bearer)\s*[:=]\s*["\'](?!.*\$\{.*\})(?!.*<YOUR).{8,}["\']'), "硬编码 Token"),
        (re.compile(r'(?i)(private_key|privatekey|secret_key|secretkey)\s*[:=]\s*["\'](?!.*\$\{.*\}).+?["\']'), "硬编码私钥"),
        (re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'), "嵌入 PEM 私钥"),
        (re.compile(r'(?i)(jwt|jwe|jws)\s*=\s*["\'][\w-]+\.[\w-]+\.[\w-]+["\']'), "硬编码 JWT Token"),
        (re.compile(r'(?i)ghp_\w{36}|gho_\w{36}|ghu_\w{36}|ghs_\w{36}'), "GitHub Token"),
        (re.compile(r'(?i)sk-[a-zA-Z0-9]{20,}'), "OpenAI API Key (sk-)"),
        (re.compile(r'(?i)AKIA[0-9A-Z]{16}'), "AWS Access Key (AKIA)"),
    ]

    # File extensions to scan
    SCAN_EXTENSIONS = {".py", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env", ".sh", ".bat", ".ps1"}

    # Paths to skip entirely
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".egg-info", "dist", "build"}

    # Line-level exemptions
    EXEMPT_PATTERNS = [
        re.compile(r"(mock|fake|dummy|placeholder|example|sample|template)", re.IGNORECASE),
        re.compile(r"<YOUR_|your-|your_"),
        re.compile(r"test_password|test_secret|test_key", re.IGNORECASE),
        re.compile(r"#\s*no-secret-check"),
    ]

    def __init__(self, config: dict, project_root: str):
        self.project_root = project_root
        self.scan_dirs = config.get("scan_dirs", ["src/", "scripts/", ".ai/config/"])
        self.severity = config.get("severity", "HIGH")
        self.whitelist = set(config.get("whitelist", []))

    def _is_exempt_line(self, line: str) -> bool:
        return any(p.search(line) for p in self.EXEMPT_PATTERNS)

    def check(self) -> Tuple[int, List[str]]:
        issues: List[str] = []
        scanned = 0

        for scan_dir in self.scan_dirs:
            full_dir = os.path.join(self.project_root, scan_dir)
            if not os.path.isdir(full_dir):
                continue
            for root, dirs, fnames in os.walk(full_dir):
                # Skip excluded dirs by mutating dirs in-place (stops os.walk)
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

                for fn in fnames:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in self.SCAN_EXTENSIONS:
                        continue

                    fpath = os.path.join(root, fn)
                    rel = os.path.relpath(fpath, self.project_root)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                    except Exception:
                        continue

                    scanned += 1
                    for lineno, line in enumerate(lines, 1):
                        stripped = line.strip()
                        # Skip comments, blank lines, exemption markers
                        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        if self._is_exempt_line(stripped):
                            continue

                        # 白名单值跳过
                        import re as _re
                        _vm = _re.search(r'["\'](.+?)["\']', stripped)
                        if _vm and _vm.group(1) in self.whitelist:
                            continue
                        _vmn = _re.match(r'^([A-Z_]+)\s*=', stripped)
                        if _vmn and _vmn.group(1) in self.whitelist:
                            continue

                        for pattern, desc in self.SECRET_PATTERNS:
                            if pattern.search(stripped):
                                # Check if value looks like a vars reference
                                if re.search(r'\$\{|env\(|os\.environ|os\.getenv', line):
                                    continue  # Actually a variable reference
                                issues.append(
                                    f"[SECRET-001] {rel}:{lineno} "
                                    f"检测到 {desc} -> "
                                    f"应从环境变量或密钥管理系统读取，请勿硬编码"
                                )
                                break  # One issue per line

        issues_count = len(issues)
        if scanned > 0 and issues_count == 0:
            pass  # Clean scan
        return issues_count, issues
