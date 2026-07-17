# _project_examples — 项目特定配置参考

此目录存放**项目自己干的事**。QA 系统只提供通用框架，
项目特有的 checker / 规则 / 工作流放在这里，供项目按需参考。

## 目录结构

```
_project_examples/
├── README.md              ← 本文件
├── checkers/              ← 项目特有 checker（17 个）
│   ├── chk_anchorchecker.py
│   ├── chk_apisignaturechecker.py
│   ├── chk_codedocsyncchecker.py
│   ├── chk_doccoveragechecker.py
│   ├── chk_docdebtratiochecker.py
│   ├── chk_docrefenforcer.py
│   ├── chk_faithfulnesschecker.py
│   ├── chk_gittraceabilitychecker.py
│   ├── chk_glossarychecker.py
│   ├── chk_hallucinationchecker.py
│   ├── chk_linkchecker.py
│   ├── chk_namingrulechecker.py
│   ├── chk_paramchecker.py
│   ├── chk_provenancechecker.py
│   ├── chk_readabilitychecker.py
│   ├── chk_schemachecker.py
│   └── chk_soxscopechecker.py
├── config/                ← 项目特有配置（16 个）
│   ├── asset_reuse_map.yaml
│   ├── content-types.yaml
│   ├── coordinator-config.yaml
│   ├── doc-build.yaml
│   ├── doc-owned.yaml
│   ├── external-docs.yaml
│   ├── feedback.yaml
│   ├── file-integrity.yaml
│   ├── fivewhy-chains.yaml
│   ├── glossary.yaml
│   ├── naming-rule.yaml
│   ├── nfr-baseline.yaml
│   ├── risk-register.yaml
│   ├── tech-debt.yaml
│   ├── token-budget.yaml
│   └── watchman-rules.yaml
├── workflows/             ← 项目特有 CI（4 个）
│   ├── ai-doc-build.yml
│   ├── ai-doc-generate.yml
│   ├── ai-doc-scan.yml
│   └── ci.yml
├── pre-commit/            ← 项目特有 pre-commit hooks 示例
│   └── hooks.yaml         (未生成，可参考 pre-commit-config.yaml 项目部分)
└── skills/                ← 项目 Skill 扫描器（44 个脚本）
    ├── skill_base.py
    ├── skill_ban_check.py
    ├── skill_layer_check.py
    ├── ...
```

## 用法

1. 把需要的 checker 从 `checkers/` 复制到项目 `scripts/` 下
2. 参照 `config/` 中的配置模板修改 `.ai/config/` 下的对应文件
3. 参照 `workflows/` 中的模板配置 `.github/workflows/` 下的 CI
4. 前三个步骤是可选的，QA 系统核心（5 个内置 checker）开箱即用

## 从 QA 系统移除的原因

| 类别 | 数量 | 原因 |
|------|------|------|
| checkers | 17 | 假定特定文档/代码目录结构，项目自有约定 |
| configs | 16 | 项目特有的术语表/命名规则/债务配置等 |
| workflows | 4 | 项目特定的文档构建/CI 编排 |
| skills | ~44 | 项目特有的代码扫描规则 |

QA 系统只提供通用框架，不替项目做约定。
