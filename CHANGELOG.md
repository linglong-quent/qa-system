# Changelog

## [4.0] - 2026-07-20
- Gate0-Gate9 十层门禁架构（替代原有 11 道门）
- 新增 SchemaValidator（文档参数↔代码常量自动比对，宪法四）
- 新增 Gate3.1 FrameworkSelfAudit（框架手册自审，分级阻断）
- 21 张 YAML 规则表（原 7 张 → 21 张）
- GitHub CI 全阻断式（A++ 标准）
- GovernanceChecker: Python 工程结构检查（PY-01~09）
- 本地 Windows 适配（run_qa.bat）
- 三仓架构落地（.github / qa-system / linglong）

## v3.0 (2026-07-17)
- Initial release as independent QA system
- 19 core checkers: inplace, lookahead, secret, deadcode, cyclic, code-ban, import-boundary, config-audit, quality-gates, claude-validation, production, codestyle, governance, securityplus, documentation, zeroprint, customrules, fusedetect, docconsistency
- 11 gates: integrity, plan, checkers, blockers, gates, pending, config, worm, agent-boundary, production, self-test
- 0-pollution architecture (QA system isolated from projects)
- GitHub branch protection: MAIN protected, PR required, 1 review
- CI/CD: lint + preflight-gate + test
