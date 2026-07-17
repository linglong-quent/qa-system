# Changelog

## v3.0 (2026-07-17)
- Initial release as independent QA system
- 19 core checkers: inplace, lookahead, secret, deadcode, cyclic, code-ban, import-boundary, config-audit, quality-gates, claude-validation, production, codestyle, governance, securityplus, documentation, zeroprint, customrules, fusedetect, docconsistency
- 11 gates: integrity, plan, checkers, blockers, gates, pending, config, worm, agent-boundary, production, self-test
- 0-pollution architecture (QA system isolated from projects)
- GitHub branch protection: MAIN protected, PR required, 1 review
- CI/CD: lint + preflight-gate + test
