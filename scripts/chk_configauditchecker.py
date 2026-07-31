#!/usr/bin/env python3
"""Checker: QA 系统自身配置审计

检查 .ai/config/ 下所有 YAML 文件的完整性与一致性。
确保：
  1. 所有配置可被 YAML 解析
  2. review-rules.yaml 中的 checker 引用都有对应模块
  3. 无多余/废弃的配置文件

统一接口: check() -> (errors: int, issues: List[str])
"""
import os, re
from typing import List, Tuple
from chk_load_yaml import load_yaml


class ConfigAuditChecker:
    """QA 配置自审检查器"""

    # 期望存在的核心配置（检查器用）
    # 不硬编码路径，只检查 review-rules.yaml 的完整性
    # 其他配置存在与否由项目自定

    def __init__(self, config: dict, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.config_dir = os.path.join(self.project_root, ".ai", "config")
        self.issues: List[str] = []
        # 0-污染模式：配置在 QA-System 中，不在项目里
        self.qa_system_root = os.environ.get("QA_SYSTEM_ROOT", "")
        self.project_name = os.environ.get("QA_PROJECT_NAME", "")
        self.zero_pollution = bool(self.qa_system_root and self.project_name)
        if self.zero_pollution:
            # 优先 {name}_local.yaml，其次 {name}.yaml
            candidates = [
                os.path.join(self.qa_system_root, ".ai", "projects", f"{self.project_name}_local.yaml"),
                os.path.join(self.qa_system_root, ".ai", "projects", f"{self.project_name}.yaml"),
            ]
            self.rules_path = next((cp for cp in candidates if os.path.exists(cp)), candidates[0])
        else:
            self.rules_path = os.path.join(self.config_dir, "review-rules.yaml")

    def check(self) -> Tuple[int, List[str]]:
        """执行配置审计检查"""
        self.issues = []
        errors = 0

        err, issues = self._check_yaml_validity()
        errors += err
        self.issues.extend(issues)

        err, issues = self._check_checker_consistency()
        errors += err
        self.issues.extend(issues)

        err, issues = self._check_config_orphans()
        errors += err
        self.issues.extend(issues)

        return errors, self.issues

    def _check_yaml_validity(self) -> Tuple[int, List[str]]:
        """检查所有 YAML 文件可解析"""
        if not os.path.isdir(self.config_dir):
            return 0, []
        errors = 0
        issues = []
        import yaml
        for f in sorted(os.listdir(self.config_dir)):
            if not f.endswith((".yaml", ".yml")):
                continue
            fpath = os.path.join(self.config_dir, f)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    yaml.safe_load(fh)
            except yaml.YAMLError as e:
                errors += 1
                issues.append(f"[CONFIG-AUDIT] {f} YAML 解析失败: {e}")
        return errors, issues

    def _check_checker_consistency(self) -> Tuple[int, List[str]]:
        """核心配置（review-rules.yaml 或 0-污染模式的 *_local.yaml）中的 checker 引用是否有对应模块"""
        rules_path = self.rules_path
        if not os.path.exists(rules_path):
            return 0, []
        config = load_yaml(rules_path)
        if not config:
            return 0, []
        errors = 0
        issues = []
        # 检查 checker 配置段对应的模块是否存在
        checker_module_map = {
            "inplace_check": "chk_inplacechecker",
            "lookahead_check": "chk_lookaheadchecker",
            "secret_check": "chk_secretchecker",
            "deadcode_check": "chk_deadcodechecker",
            "cyclic_check": "chk_cyclicchecker",
            "code_ban_check": "chk_codebanchecker",
            "import_boundary_check": "chk_importboundary",
        }
        # scripts/ 在 QA-System 中（0-污染模式或 QA_SYSTEM_ROOT 已指定），否则在项目根
        # 检查器脚本属于 QA-System 而非被测项目，因此只要 QA_SYSTEM_ROOT 可用即优先使用其 scripts/
        scripts_dir = (os.path.join(self.qa_system_root, "scripts")
                       if self.qa_system_root
                       else os.path.join(self.project_root, "scripts"))
        config_label = os.path.basename(rules_path)
        for config_key, module_name in checker_module_map.items():
            section = config.get(config_key)
            if section is None:
                errors += 1
                issues.append(f"[CONFIG-AUDIT] {config_label} 缺少 '{config_key}' 段")
                continue
            mod_path = os.path.join(scripts_dir, f"{module_name}.py")
            if not os.path.exists(mod_path):
                errors += 1
                issues.append(f"[CONFIG-AUDIT] '{config_key}' 引用了 {module_name}.py 但文件不存在")
        return errors, issues

    def _check_config_orphans(self) -> Tuple[int, List[str]]:
        """检查废弃配置（不在预期列表中的 .yaml）"""
        if not os.path.isdir(self.config_dir):
            return 0, []
        expected = {
            # v3.0 存量
            "review-rules.yaml", "secrets-scan.yaml", "dead-code.yaml",
            "ai-pipeline.yaml", "ai-whitelist.yaml", "arch-review.yaml",
            # v4.0 新增（21 张规则表）
            "quality-plan.yaml", "nfr-baseline.yaml",
            "deployment-gates.yaml", "issue-template.yaml", "retro-gates.yaml",
            "schema-validator.yaml", "framework-self-audit.yaml",
            "codeowner-rules.yaml", "security-baseline.yaml",
            "performance-baseline.yaml", "test-coverage.yaml",
            "change-management.yaml", "worm-policy.yaml",
            "agent-boundary.yaml", "compliance-mapping.yaml",
        }
        errors = 0
        issues = []
        for f in os.listdir(self.config_dir):
            if not f.endswith((".yaml", ".yml")):
                continue
            if f not in expected:
                issues.append(f"[CONFIG-AUDIT] 未注册的配置: {f} — 如已废弃请删除或加入预期列表")
        return errors, issues
