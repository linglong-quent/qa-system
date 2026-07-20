# QA System v4.0

独立质量工程系统 — 玲珑量化治理子系统。0-污染双模运行，Gate0-Gate9 十层门禁。

## 架构

```
玲珑量化框架手册 → QA-SYS v4.0 实现
┌──────────────────────────────────────────────────────────┐
│  Gate0  AI-First / Issue    — Issue 模板+PR关联   (已实现) │
│  Gate1  Position            — 文档位置校验         (自动化) │
│  Gate2  Naming              — 文档命名校验         (自动化) │
│  Gate3  Sync                — SchemaValidator + 目录      │
│  Gate3.1 Framework Self-Audit— 框架手册自审   (权重错阻断) │
│  Gate4  Version & WORM      — Git 哈希 + Append-Only     │
│  Gate5  Scoring & Checkers  — 19 检测器 + 评分           │
│  Gate6  Permission          — CODEOWNERS + 权限边界      │
│  Gate7  Closed-Loop         — 违规→申诉→迭代             │
│  Gate8  Deployment          — 生产就绪+CHANGELOG+版本     │
│  Gate9  Compliance & Retro  — 合规+自检+复盘             │
└──────────────────────────────────────────────────────────┘
```

## 快速开始

```bash
# 本地全流程（检查+门禁）
python scripts/qa.py local

# 全量检查
python scripts/qa_check.py health

# 十层门禁
python scripts/qa_gate.py

# 单门禁运行
python scripts/qa_gate.py --gate=3     # SchemaValidator
python scripts/qa_gate.py --gate=3.1   # 框架手册自审

# 一键接入新项目（仅生成 .pre-commit-config.yaml 引用，不复制 QA 代码）
python scripts/qa_setup.py --project /path/to/project --local-windows

# 设置环境变量（替代硬编码路径）
set QA_SYSTEM_ROOT=E:\WB\QA-System
```

## 使用（CI 引用）

```yaml
- name: Load QA System v4.0
  run: git clone --depth 1 https://github.com/linglong-quent/qa-system.git /opt/qa-system

- name: QA Gate
  run: python /opt/qa-system/scripts/qa_gate.py
```

## 规则底座 — 21 张 YAML 规则表

| 配置 | 用途 |
|------|------|
| review-rules.yaml | 核心评分 + 19 checker 配置 |
| quality-plan.yaml | PDCA 质量规划 |
| nfr-baseline.yaml | 非功能性需求基线 |
| deployment-gates.yaml | 部署门禁 |
| issue-template.yaml | Issue 模板规范 |
| retro-gates.yaml | 复盘门禁 |
| schema-validator.yaml | 文档↔代码参数对比 |
| framework-self-audit.yaml | 框架手册自审 |
| codeowner-rules.yaml | 权限矩阵 |
| security-baseline.yaml | OWASP + NASA 10 |
| performance-baseline.yaml | 性能基线 |
| test-coverage.yaml | 测试覆盖门禁 |
| change-management.yaml | 变更管理 + 反漂移 |
| worm-policy.yaml | WORM 归档策略 |
| agent-boundary.yaml | AI Agent 边界 |
| compliance-mapping.yaml | ISO/SOX/SLSA 映射 |
| secrets-scan.yaml | 密钥扫描 |
| dead-code.yaml | 死代码扫描 |
| ai-pipeline.yaml | AI 管线 |
| ai-whitelist.yaml | AI 白名单 |
| arch-review.yaml | 架构评审 |

## 核心能力

| 能力 | 说明 |
|------|------|
| 19 个内置 Checker | 消费 21 张 YAML 规则表的配置，执行静态分析与合规检查 |
| 代码行数门禁 | STYLE-01~06：PEP 8 / NASA Power of 10 / ISO 25010 |
| SchemaValidator | 文档参数 ↔ 代码常量自动比对 (宪法四) |
| Gate3.1 框架自审 | 权重/概念/来源/版本完整性检查（权重错误→BLOCKER） |
| 4 级干预 | BLOCKER / WARN / INFO / PASS |
| 3 层 Checker 架构 | 内置通用 + 项目插件 + CI/CD 集成 |
| 双模运行 | 本地 pre-commit / CI git clone / 生产跳过 |
| 0-污染 | QA 代码不进项目目录，通过环境变量定位 |
| AI Agent 原生 | qa-report.json → pending.json → AI 自动修复 |

## 标准对齐

ISO 25010 / NASA Power of 10 / OWASP / CMMI / SOX / SLSA Level 2

## 版本

v4.0 — Gate0-Gate9 十层门禁 · SchemaValidator · 21 规则表 · 框架自审 · 本地 Windows 适配

> 融合自玲珑量化框架手册 v4.0 设计规范与 QA System v3.0 实现代码。
