# QA 系统 — 全自动流程闭环与联接

> 本文档说明了 QA 系统在本地电脑与 GitHub 之间的完整流程。
> 只说明架构和联接方式，不涉及工具内部实现。

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  本地电脑（Windows/Linux/macOS）                                      │
│  ┌──────────┐   ┌─────────┐   ┌────────┐   ┌────────┐   ┌────────┐  │
│  │ Plan     │ → │ Agent   │ → │ Check  │ → │ Gate   │ → │ Commit │  │
│  │ 配置文件  │   │ 智能体  │   │ 自动检查 │   │ 自动门控│   │ 提交   │  │
│  └──────────┘   └─────────┘   └────────┘   └────────┘   └────────┘  │
│       │              │              │            │            │      │
│       ▼              ▼              ▼            ▼            ▼      │
│  本地文件修改    读标准写代码    pre-commit    阻断或通过    git push │
└──────────────────────────────────────────────────────────────────────┘
                                    │ git push
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  GitHub                                                              │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  pull_request 触发 → GitHub Actions 运行完整 QA 管线            │  │
│  │  P0: 自检 → P1: 10 checker → P2: 分类 → P3: 总闸门              │  │
│  │  → ALLOW: PR 可合并 / DENY: PR 被阻断 + 自动评论                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  每日 02:00 UTC 全量扫描 + 质量趋势跟踪 + 反馈回路                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 二、本地电脑端

### 2.1 前置条件

| 条件 | 说明 |
|------|------|
| Python 3.12+ | 运行时 |
| pre-commit | 钩子管理器 |
| pyyaml | 配置解析 |
| Git | 版本控制 |

### 2.2 安装

```
pip install pre-commit pyyaml
pre-commit install
python scripts/qa_setup.py --project <项目路径>
```

### 2.3 全自动流程

```
[Plan 层 — 被动加载]
  .ai/config/review-rules.yaml    ← checker 行为配置
  .ai/config/quality-plan.yaml    ← 质量目标定义
  .ai/prompts/CLAUDE.md           ← AI 编码约束

[Agent 层 — 智能体执行]
  人/AI 编码助手 读 CLAUDE.md → 按标准生成代码
  此处是唯一的人/智能体介入点

[Check 层 — 全自动]
  pre-commit 触发 15 道钩子（无需人工干预）
  10 个 checker 并行执行
  检查结果写入 .ai/logs/qa-report.json
  问题分类写入 .ai/fixes/pending.json

[Gate 层 — 全自动]
  qa_gate.py 检查 8 道门
  全部通过 → 允许提交
  任意不过 → 阻断提交

[修复回环 — 人/AI 介入]
  门控阻断后，智能体读 pending.json
  按结构化指导修代码
  重新触发 pre-commit → 直到通过
```

### 2.4 工具点

| 触发时机 | 工具 | 自动/手动 |
|---------|------|----------|
| git commit | pre-commit 15 钩子 | 自动 |
| 手动 | `python scripts/qa_check.py health` | 手动 |
| 手动 | `python scripts/qa_classify.py` | 手动 |
| 手动 | `python scripts/qa_gate.py` | 手动 |
| 手动 | `python scripts/qa_plan.py feedback` | 手动 |
| 阻断后 | 读 `.ai/fixes/pending.json` | 智能体手动 |
| 初始化 | `python scripts/qa_setup.py` | 一次性 |

### 2.5 人/智能体关键决策点

| 环节 | 决策内容 | 频次 |
|------|---------|------|
| 写代码时 | 遵循 CLAUDE.md 标准 | 每次生成 |
| Gate 阻断后 | 读 pending.json，按指导修 | 每次阻断 |
| Plan 反馈后 | 确认是否升级标准/更新路径 | 每月/季度 |
| 初始安装时 | 配置 scan_dirs 指向实际目录 | 一次性 |

---

## 三、GitHub 端

### 3.1 前置条件

| 条件 | 说明 |
|------|------|
| GitHub Actions | CI 运行环境 |
| Python 3.12 | runner 预装 |
| pyyaml | pip install |

### 3.2 全自动流程（PR 触发）

```
[Trigger]
  pull_request → .github/workflows/ai-code-review.yml

[P0: 自检 — 全自动]
  python scripts/qa_self_test.py
  验证 QA 系统自身完整性
  失败不影响后续，仅报告

[P1: 全量检查 — 全自动]
  python scripts/qa_check.py health
  10 个 checker 在 Linux runner 上执行
  检查所有被 PR 修改的文件
  输出: .ai/logs/qa-report.json

[P2: 分类 — 全自动]
  python scripts/qa_classify.py
  将问题分类为智能体可执行的修复任务
  输出: .ai/fixes/pending.json

[P3: 总闸门 — 全自动]
  python scripts/qa_gate.py
  8 道门独立检查
  ALLOW → PR 可合并
  DENY  → exit 1 → PR 被 GitHub 标记为失败

[PR 评论 — 全自动]
  GitHub Script 自动读取 qa-report.json + pending.json
  在 PR 上生成结构化评论

[Artifact 存档 — 全自动]
  qa-report.json / pending.json / quality-plan.yaml
  存档 7 天（PR）或 90 天（每日扫描）
```

### 3.3 全自动流程（定时触发）

```
[Trigger]
  每日 UTC 02:00 → .github/workflows/ai-nightly-scan.yml

[全自动管线]
  自检 → 全量检查 → 分类 → 反馈回路 → 总闸门

[反馈回路输出]
  qa_plan.py feedback 比较本次与上次结果
  输出规划更新建议（标准升降级 / 路径过期提醒）

[存档]
  报告存档 90 天，支持质量趋势分析
```

### 3.4 工具点

| 触发时机 | 工具 | 自动/手动 |
|---------|------|----------|
| PR 提交 | ai-code-review.yml | 自动 |
| 每日凌晨 | ai-nightly-scan.yml | 自动 |
| 手动触发 | workflow_dispatch | 手动 |
| PR 被阻断 | 读 GitHub Actions 日志 | 智能体手动 |

### 3.5 人/智能体关键决策点

| 环节 | 决策内容 | 频次 |
|------|---------|------|
| PR 被阻断 | 读 PR 评论中的 pending.json，修代码 | 每次阻断 |
| 读 Nightly 报告 | 查看质量趋势 | 每日 |
| 确认反馈建议 | 是否升级 BLOCKER / 更新路径 | 每月 |

---

## 四、本地 ↔ GitHub 联接

### 4.1 代码同步

```
本地 commit → git push → GitHub Actions 触发 → PR 检查
                                                    ↓
PR 阻断 → 本地修 → git commit --amend → git push --force
                                                    ↓
PR 通过 → merge → main 分支更新 → 本地 git pull
```

### 4.2 报告传递

| 产出 | 本地路径 | GitHub 路径 | 用途 |
|------|---------|------------|------|
| QA 报告 | `.ai/logs/qa-report.json` | 同路径 | 检查结果 |
| 修复任务 | `.ai/fixes/pending.json` | 同路径 | 智能体读 |
| 质量规划 | `.ai/config/quality-plan.yaml` | 同路径 | 门控依据 |
| PR 评论 | 无 | GitHub API | 通知开发者 |

### 4.3 状态传递

```
本地 pre-commit DENY  → 不在本地 commit → 不会 push → 不会到 GitHub
本地 pre-commit ALLOW → 本地 commit → git push → GitHub PR 触发

本地是 GitHub 的前置过滤器：
  本地没通过的 commit，根本到不了 GitHub
  GitHub 跑的是本地已通过的那一轮 + 额外的环境差异检查
```

---

## 五、全自动化 vs 人工干预

### 全自动化（无需人介入）

| 环节 | 自动化程度 |
|------|-----------|
| Plan 加载 | 文件存在即可，自动被 checker 读取 |
| pre-commit 检查 | 15 道钩子自动执行 |
| CI 全量检查 | P0-P4 全自动 |
| 问题分类 | qa_classify 自动分类 |
| 总闸门 | qa_gate 自动判断 ALLOW/DENY |
| PR 评论 | GitHub Script 自动生成 |
| Artifact 存档 | 自动上传 |

### 需人工/智能体介入

| 环节 | 做什么 |
|------|--------|
| **写代码** | 智能体按 CLAUDE.md 标准生成（人/AI） |
| **修复阻断** | 读 pending.json，按指导修改代码（人/AI） |
| **确认反馈** | 是否收紧标准/更新规划路径（人决策） |
| **初始化配置** | scan_dirs 指向实际代码目录（一次性/人） |
| **质量门阈值** | 什么算 BLOCKER / 什么算 WARN（人决策） |

---

## 六、关键原则

1. **本地是 GitHub 的前置过滤器** — 本地没过的 commit 到不了 GitHub
2. **GitHub 是本地后的第二道防线** — 环境差异、合并冲突、全量扫描
3. **人只在规划层和修复层介入** — Check 和 Gate 全自动
4. **不产出不良品** — Gate DENY 阻止一切不合格提交
5. **不漏检不良品** — 本地 15 道 + GitHub P0-P4 双重验证
6. **全流程文件化** — 配置、报告、分类、门控、反馈，全部以文件形式传递
