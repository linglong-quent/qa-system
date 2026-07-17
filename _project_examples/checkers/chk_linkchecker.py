#!/usr/bin/env python3
"""Extracted: LinkChecker"""
import os, re
from typing import List, Tuple


class LinkChecker:
    """扫描 Markdown 中的 URL 和相对路径，检测链接存活"""

    # Markdown 链接正则: [text](url)
    LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    # 代码块标记
    CODE_FENCE_PATTERN = re.compile(r"```")

    def __init__(self, config: dict, project_root: str):
        """
        初始化链接检测器

        Args:
            config: review-rules.yaml 中 link_check 配置段
            project_root: 项目根目录
        """
        self.timeout = config.get("timeout", 5)
        self.alive_status = set(config.get("alive_status", [200, 301, 302, 307, 308]))
        self.whitelist = config.get("whitelist", [])
        self.project_root = project_root

    def check(self, md_file: str) -> Tuple[int, List[str]]:
        """
        检测单个 Markdown 文件的链接存活

        Args:
            md_file: Markdown 文件路径

        Returns:
            (扣分数, 问题列表)
        """
        issues = []
        deduction = 0
        max_deduction = 15  # V2.0: link_alive 满分 15
        per_issue = 5

        if not os.path.exists(md_file):
            return 0, [f"文件不存在: {md_file}"]

        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 移除代码块内容（代码块内的链接不检测）
        lines = content.split("\n")
        in_code_block = False
        clean_lines = []
        for line in lines:
            if self.CODE_FENCE_PATTERN.search(line):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                clean_lines.append(line)

        clean_content = "\n".join(clean_lines)

        # 提取所有链接
        links = self.LINK_PATTERN.findall(clean_content)

        for text, url in links:
            # 跳过白名单
            if self._is_whitelisted(url):
                continue

            # 判断是内链还是外链
            if url.startswith("http://") or url.startswith("https://"):
                alive = self._check_external(url)
            else:
                alive = self._check_internal(url, md_file)

            if not alive:
                issues.append(f"死链: [{text}]({url})")
                deduction = min(deduction + per_issue, max_deduction)

        return deduction, issues

    def _is_whitelisted(self, url: str) -> bool:
        """检查 URL 是否在白名单中"""
        for pattern in self.whitelist:
            # 简单通配符匹配
            if "*" in pattern:
                regex = pattern.replace("*", ".*")
                if re.match(regex, url):
                    return True
            elif url.startswith(pattern):
                return True
        return False

    def _check_external(self, url: str) -> bool:
        """检测外链存活（HEAD 请求）"""
        try:
            req = urllib.request.Request(url, method="HEAD")
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            return resp.status in self.alive_status
        except Exception:
            # HEAD 不支持时尝试 GET
            try:
                req = urllib.request.Request(url, method="GET")
                resp = urllib.request.urlopen(req, timeout=self.timeout)
                return resp.status in self.alive_status
            except Exception:
                return False

    def _check_internal(self, path: str, md_file: str) -> bool:
        """检测内链（相对路径）是否存在"""
        # 去除锚点部分
        if "#" in path:
            path = path.split("#")[0]
        if not path:
            return True  # 纯锚点链接，视为存在

        # 相对于 Markdown 文件所在目录解析路径
        base_dir = os.path.dirname(md_file)
        target = os.path.normpath(os.path.join(base_dir, path))
        return os.path.exists(target)
