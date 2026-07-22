# 玲珑量化 · GitHub 工作指南

> 2026-07-20 v2 | 三仓架构 · 人机共治 · 0 污染

---

## 一、三仓架构总览

```
组织: github.com/linglong-quent
│
├── .github                     ← 组织级工作流（触发层）
│   └── workflows/qa-gate.yml   ← 一次配置，所有仓库自动继承
│
├── qa-system                   ← QA 系统（治理层）
│   ├── scripts/     — 19 checker + Gate0-Gate9 引擎
│   ├── .ai/config/  — 21 张 YAML 规则表（配置定义）
│   └── .github/     — QA 系统自身的 CI
│
└── linglong                     ← 量化项目（业务层 · 0 污染）
    ├── src/         — 策略代码
    ├── scripts/    — 工具脚本
    └── .pre-commit-config.yaml — 引用外部 QA 系统（不内嵌 QA 逻辑）
```

### 各仓职责

| 仓库          | 负责人     | 存放内容                                      | 原则              |
| ----------- | ------- | ----------------------------------------- | --------------- |
| `.github`   | 金哥      | 组织级工作流 YAML                               | 只触发、不包含逻辑       |
| `qa-system` | 昤宝宝（QA） | 81 个文件：19 checker + 21 规则表 + Gate 引擎 + CI | QA 代码全部在这里      |
| `linglong`  | 金哥 + CB | 策略代码 + 依赖文件                               | 0 污染，不放任何 QA 文件 |

### 各仓怎么用

#### `.github` — 组织级触发

```
用途：linglong 提 PR 时自动触发 QA 检查
维护：改一次，所有仓库继承
保护：main 已开启保护（禁止直推）
文件：.github/workflows/qa-gate.yml（唯一文件，501 字节）
操作：一般不需要动。如果要改触发规则，直接推 PR
```

#### `qa-system` — QA 系统核心

```
用途：运行 QA 检查、维护规则表、管理 checker
本地位置：E:\WB\QA-System
CI 触发：推 main 自动触发 6 步全阻断
保护：main 需 QA Self-Test 通过 + PR review + 禁止 force push
日常操作：
  - 改规则表 → 改 .ai/config/*.yaml → PR → CI 绿 → 合并
  - 改 checker → 改 scripts/chk_*.py → PR → CI 绿 → 合并
  - 本地测试 → cd E:\WB\QA-System && python scripts/qa_self_test.py
  - 检查 linglong → python scripts/qa_check.py health --project E:\linglong
```

#### `linglong` — 策略代码仓库（0 污染）

```
用途：纯策略代码 + 依赖配置
本地位置：E:\linglong
CI 触发：提 PR 时由 .github 工作流触发
保护：main 需 lint + preflight-gate + test 通过 + 1 review
原则：不放任何 QA 文件（qa_* / chk_* / .ai/ 均不允许）
当前状态：4 个文件（.github/risk-tier-contract.json + .gitignore + requirements.txt）
操作：正常写策略、提 PR、等 CI 绿、合并
```

| `qa-system` | 昤宝宝 | Checker、Gate、规则表 | 独立仓库、0 污染     |  
| `linglong`  | 金哥  | 策略代码、工具脚本        | 纯业务、0 QA 逻辑残留 |

---

## 二、人机共治角色

| 角色      | 实体        | 写什么                                     | 不做什么               |
| ------- | --------- | --------------------------------------- | ------------------ |
| **架构师** | KUN (AI)  | `.md` 设计文档、`.schema.json` 契约、`.yaml` 规则 | 不写 `.py` 代码        |
| **程序员** | CB (AI)   | `.py` 代码、测试、CI 配置、部署脚本                  | 不修改规则表             |
| **决策者** | **金哥（你）** | 审文档、定规则、管资金                             | 不写代码、不 review diff |
| **QA**  | **昤宝宝**   | QA 系统维护、门禁、报告                           | 不写策略代码             |

---

## 三、完整工作流

### 3.1 日常开发流程

```
金哥 → 发需求（Issue）
  ↓
KUN → 出设计文档（docs/ADR/*.md, *.schema.json）
  ↓
金哥 → 审文档（不审代码！）
  ↓ 批准
CB → 按文档写代码 + 测试
  ↓
Pre-commit 本地拦截
  ├── black/isort/flake8/mypy（代码规范）
  └── QA Gate（Gate3 目录规范 + Gate5 评分）
  ↓ 通过
Push → GitHub
  ↓
组织级工作流 qa-gate.yml 触发
  ├── P0: QA Self-Test（阻断式）
  ├── P1: QA Full Check（19 checker, 消费21规则表）
  ├── P2: Gate3 SchemaValidator（文档↔代码参数比对）
  ├── P3: Gate3.1 框架自审（权重错误→BLOCKER，其余WARN）
  └── P4: QA Gate Gate0-Gate9（报告用）
  ↓ 通过
PR 可合并 → Squash Merge → main
  ↓
重新触发 CI → 全量检查 → 完成
```

### 3.2 评审六阶段闭环

```
① 自审        — CB 自查代码与文档一致性
    ↓
② 架构评审    — KUN 审架构 + 金哥审 .md 文档
    ↓
③ 量化评审    — QA-SYS 自动触发 Gate0-Gate9
    ↓
④ 回测验证    — CB 执行回测，KUN 生成/审核回测报告（.md）
                  金哥审批回测报告（不看回测代码）
                  重点：样本区间、手续费滑点、归因分析
    ↓
⑤ 灰度        — QMT 仿真 1 天 + 人工确认
    ↓
⑥ 复盘        — 日志检查、周复盘、月审计 → 结论→下一轮需求
```



---

## 四、分支策略

| 分支          | 用途     | 保护规则                                |
| ----------- | ------ | ----------------------------------- |
| `main`      | 生产就绪代码 | ✅ QA Self-Test 必须通过 · 禁止 force push |
| `develop`   | 日常开发   | ⚠️ PR 到 main 需 CI 通过                |
| `feature/*` | 功能分支   | 无保护，从 develop 开出                    |
| `fix/*`     | 修复分支   | 无保护                                 |

**禁止直接 push main**。所有变更走 PR → CI → Squash Merge。

---

## 五、PR 规范

### 5.1 PR 内容规范

每个 PR 必须符合 **宪法五：单一逻辑变更**

- 一个 PR 只能对应一个 `.md` 文件的逻辑变更
- 关联文件联动更新（如改参数同时改测试用例）允许，但必须在 PR 描述标注

### 5.2 PR 描述模板

```markdown
## 变更摘要

**关联文档**: docs/ADR/xxx.md

**变更内容**:
- 修改了什么
- 为什么改

**影响范围**:
- 影响的模块
- 是否需要回测

**验证**:
- [ ] 本地 self-test 通过
- [ ] 回测验证（CB 执行，KUN 审核报告，金哥审批）
```

### 5.3 回测报告责任

回测报告必须由 KUN 生成或审核，**金哥审批报告内容**（不看回测代码）：

| 环节      | 责任人    | 产出         |
| ------- | ------ | ---------- |
| 执行回测    | CB     | 回测数据       |
| 生成/审核报告 | KUN    | `.md` 回测报告 |
| 审批报告    | 金哥     | 决策记录       |
| 归档      | QA-SYS | WORM 归档    |

重点审核：样本区间、手续费和滑点设置、归因分析。

### 5.4 反文档漂移规则

文档变更描述中，禁止以下模糊词汇：

```
❌ "优化" · "调整" · "修复" · "改进" · "完善"
✅ 必须写明具体数值或逻辑变更
```

错误示例：`优化了 L4 安全垫算法`  
正确示例：`将 L4 安全垫阈值从 0.5 调整为 0.6, 当 DD > 10% 时触发`

---

## 六、CI 门禁详解

### 6.1 Gate0-Gate9 十层门禁（本地 + CI 双通道）

| 门禁      | 名称               | CI 阻断               | 本地阻断                      | 说明                              |
| ------- | ---------------- | ------------------- | ------------------------- | ------------------------------- |
| Gate0   | AI-First / Issue | ✅ CI: Gate0 step    | ✅ pre-commit: qa-gate     | Issue 模板 + PR 关联                |
| Gate1   | 文档位置             | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | 映射规则 + 白名单                      |
| Gate2   | 文档命名             | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | 命名表 + 正则校验                      |
| Gate3   | 文档同步             | ✅ CI: Gate3 step    | ✅ pre-commit: qa-boundary | SchemaValidator + 目录 + 越域import |
| Gate3.1 | 框架自审             | ✅ CI: Gate3.1 step  | ✅ pre-commit: qa-gate     | 权重错误→BLOCKER, 其余WARN            |
| Gate4   | 版本与 WORM         | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | Git 哈希 + Append-Only            |
| Gate5   | 评分检测             | ✅ CI: QA Full Check | ✅ pre-commit: qa-health   | 19 checker 阻断, 元检查仅报告           |
| Gate6   | 权限               | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | CODEOWNERS + Agent边界            |
| Gate7   | 闭环               | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | 违规→申诉→迭代                        |
| Gate8   | 部署               | ✅ CI: QA Gate       | ✅ pre-commit: qa-prod     | 生产 + CHANGELOG + 版本 + SOP       |
| Gate9   | 合规自检             | ✅ CI: QA Gate       | ✅ pre-commit: qa-gate     | 系统自检 + 复盘闭环                     |



> Gate3.1 分级逻辑：权重逻辑错误（如趋势+形态+…≠100%）→ **BLOCKER**；概念缺失、版本号缺失 → **WARN**；来源标注覆盖率低 → **INFO**。

### 6.2 干预级别

| 级别          | 含义    | CI 行为      |
| ----------- | ----- | ---------- |
| **BLOCKER** | 必须修复  | ❌ 阻断 PR    |
| **WARN**    | 需人工确认 | ⚠️ 不阻断，但标记 |
| **INFO**    | 建议性提示 | ℹ️ 仅供参考    |
| **PASS**    | 完全通过  | ✅ 无操作      |

### 6.3 代码行数门禁 — 行业标准

| 检查   | 代号       | 规则                      | 标准来源                   |
| ---- | -------- | ----------------------- | ---------------------- |
| 行长度  | STYLE-02 | 每行 ≤ 120 字符             | PEP 8                  |
| 函数行数 | STYLE-06 | 每个函数 ≤ 60 行             | NASA Power of 10       |
| 文件行数 | STYLE-05 | 每个文件 ≤ 500 行            | ISO 25010 / Clean Code |
| 文件名  | STYLE-01 | 小写+下划线                  | Python 社区惯例            |
| 函数命名 | STYLE-03 | snake_case / PascalCase | PEP 8                  |
| 日志格式 | STYLE-04 | % 格式化而非 f-string        | 框架手册约定                 |

> 阈值从 `.ai/config/nfr-baseline.yaml` 读取，修改规则表即生效，无需改 checker 代码。

### 6.4 19 Checker 与 21 规则表的关系

```
21 张 YAML 规则表 ──── 定义 ────→ 检查参数、阈值、启停开关
                                    ↓ 消费
19 个内置 Checker ──── 执行 ────→ 具体静态分析与合规检查
```

规则表决定**检查什么**（参数、阈值、白名单），Checker 决定**怎么检查**（AST解析、正则匹配、边界校验）。

### 6.5 查看 MAIN 保护规则

GitHub 有两种规则系统，**规则在 Branch Protection 里，不在 Rulesets**：

| 系统                      | 位置                    | 当前状态     |
| ----------------------- | --------------------- | -------- |
| **Branch Protection** ✅ | `Settings → Branches` | 规则在这里    |
| Rulesets ❌              | `Settings → Rules`    | 未配置（不需要） |

**正确查看路径：**

```
仓库主页 → Settings → Branches → Branch protection rules
```

或直接打开：

- **qa-system**: `https://github.com/linglong-quent/qa-system/settings/branches`
- **linglong**: `https://github.com/linglong-quent/linglong/settings/branches`
- **.github**: `https://github.com/linglong-quent/.github/settings/branches`

点 **main** 旁边的 **Edit** 查看全部规则。

点 main 旁边的 **Edit** 查看详情。

**检查重点项：**

| 规则                                      | 说明                                                                   |
| --------------------------------------- | -------------------------------------------------------------------- |
| ✅ **Require status checks**             | 必须选择 `QA Self-Test`（qa-system）或 `lint/preflight-gate/test`（linglong） |
| ✅ **Require branches to be up to date** | PR 分支必须基于最新 main                                                     |
| ✅ **Require pull request reviews**      | 至少 1 人 Approve                                                       |
| ✅ **Dismiss stale reviews**             | 新提交自动清除旧 Review                                                      |
| ✅ **Include administrators**            | Admin 也需要遵守规则                                                        |
| ✅ **Do not allow bypassing**            | 禁止绕过（repo rules）                                                     |
| ✅ **Block force pushes**                | 禁止 force push                                                        |

> 如果保护规则被绕过（如直推 main），CI 不会触发，main 会变红，修复后必须重新走 PR 流程。

---

## 七、QA 系统使用

### 7.1 本地运行

```bash
# 从 qa-system 仓库运行
cd E:\WB\QA-System

# 全流程（检查 + 门禁）
python scripts/qa.py local

# 单门禁
python scripts/qa_gate.py --gate=3      # SchemaValidator
python scripts/qa_gate.py --gate=3.1    # 框架自审（分级阻断）
python scripts/qa_gate.py --gate=5      # 评分检测

# 全量检查
python scripts/qa_check.py health

# 十层门禁
python scripts/qa_gate.py

# Windows 一键启动
run_qa.bat
```

### 7.2 环境变量（替代硬编码路径）

| 变量                    | 用途           | 示例                |
| --------------------- | ------------ | ----------------- |
| `QA_SYSTEM_ROOT=<路径>` | QA 系统根目录     | `E:\WB\QA-System` |
| `QA_PROJECT=<路径>`     | 指定目标项目       | `E:\linglong`     |
| `QA_ENV=production`   | 生产模式（门禁自动通过） |                   |
| `QA_PROJECT_NAME=<名>` | 目标项目名        | `linglong_github` |

**必须设置** `QA_SYSTEM_ROOT` 环境变量，所有 `.pre-commit-config.yaml` 通过该变量引用 QA 系统路径，禁止硬编码。

**Windows 设置**：

```cmd
setx QA_SYSTEM_ROOT "E:\WB\QA-System"
```

**pre-commit 配置示例**：

```yaml
# .pre-commit-config.yaml — 只引用，不包含 QA 逻辑
repos:
  - repo: local
    hooks:
      - id: qa-health
        name: qa-health (QA 系统)
        entry: python %QA_SYSTEM_ROOT%/scripts/qa_check.py health
        language: system
        pass_filenames: false
```

---

## 八、0 污染原则

### 8.1 量化项目（linglong）允许/禁止清单

| 允许                                    | 禁止                                 |
| ------------------------------------- | ---------------------------------- |
| `.github/risk-tier-contract.json`     | `.ai/` 任何目录                        |
| `.pre-commit-config.yaml`（引用外部 QA 路径） | `qa_*.py` / `chk_*.py`             |
| `requirements.txt`                    | `.pre-commit-config.yaml` 中的 QA 逻辑 |
| `src/`、`scripts/`                     | `.cursorrules`                     |
| `.github/workflows/`（仅组织级继承）          | 任何内嵌的 QA 逻辑                        |

### 8.2 qa_setup.py 的正确用法

`qa_setup.py` **只做一件事**：在目标项目中生成 `.pre-commit-config.yaml` 引用。

它**不会**往业务仓库里复制 Checker 脚本。如需复制（嵌入式模式），需显式指定 `--with-checkers`，但该模式**仅适用于非 linglong 的独立项目**。

```bash
# 正确：仅生成引用配置（linglong 项目）
python scripts/qa_setup.py --project /path/to/linglong

# 仅用于独立项目（非 linglong）：
python scripts/qa_setup.py --project /path/to/other --with-checkers
```

---

## 十、自检：三个仓库状态是否正常

不需要问我，自己跑一遍下面的命令就能知道所有仓库是否正常。

### 10.1 一键自检

在 PowerShell 或终端运行：

```bash
# ====================================
# 三仓自检脚本
# ====================================

echo "=== qa-system 自检 ==="
# 本地自测
cd E:\WB\QA-System && python scripts/qa_self_test.py | tail -3

# 本地门禁
python scripts/qa_gate.py | tail -3

# 远程 CI 状态
curl -s https://api.github.com/repos/linglong-quent/qa-system/actions/runs?per_page=1 | python -c "import json,sys; r=json.load(sys.stdin); print(f'CI: {r[\"workflow_runs\"][0][\"conclusion\"]}' if r.get('workflow_runs') else 'CI: 无')"

# 保护规则
curl -s https://api.github.com/repos/linglong-quent/qa-system/branches/main/protection | python -c "import json,sys; p=json.load(sys.stdin); print(f'保护: OK' if p.get('required_status_checks') else '保护: 无')"

echo ""
echo "=== linglong 0 污染检查 ==="
# 检查是否有 QA 文件残留
cd E:\linglong
python -c "
import os
qa_files = []
for root, dirs, files in os.walk('.'):
    for f in files:
        if f.startswith(('qa_','chk_')) or '.ai/' in root:
            qa_files.append(os.path.join(root,f))
if qa_files:
    print(f'污染: {len(qa_files)} 个 QA 文件!')
    for f in qa_files: print(f'  {f}')
else:
    print('0 污染: ✅ 无 QA 文件')
"

echo ""
echo "=== .github 检查 ==="
curl -s https://api.github.com/repos/linglong-quent/.github/contents/.github/workflows | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} 个工作流文件' if isinstance(d,list) else '文件: 正常')"
```

### 10.2 快速目视检查（不开命令行）

打开浏览器，看三个页面的颜色：

| 仓库                  | 看什么                                                   | 正常状态                       |
| ------------------- | ----------------------------------------------------- | -------------------------- |
| `qa-system` Actions | <https://github.com/linglong-quent/qa-system/actions> | ✅ 绿色勾                      |
| `linglong` 根目录      | <https://github.com/linglong-quent/linglong>          | 只有配置文件名，无 `.ai/` 目录        |
| `.github` 文件        | <https://github.com/linglong-quent/.github>           | 只有 `workflows/qa-gate.yml` |

### 10.3 判断标准

```
qa-system CI 绿 + 本地 self-test 通过 + 门禁全绿 = QA 系统正常
linglong 无 qa_*/chk_*/.ai/ 文件 = 0 污染正常
.github 只有一个 qa-gate.yml = 触发层正常
```

任何一个红了就说明有问题——找问题出在哪，修好再继续。

### 9.1 盘中紧急修复

```
盘中问题 → 影响交易？
  ├── 是 → 紧急熔断 → OPS 锁账户 → 修复 → 跳过 CI → 人确认 → 热更新
  │         ↓
  │         【事后 1 小时内必须补交 Hotfix PR】
  │         └── 包含：①代码变更 ②对应文档变更（遵循反漂移规则）
  │         └── 需通过除性能测试外的所有门禁
  │         └── 用于归档和复盘
  └── 否 → 记录 → 盘后标准流程
```

**Hotfix PR 要求**：

1. 包含完整的代码变更
2. 包含对应的文档变更（参数修改必须更新文档）
3. 人工审批记录
4. 通过 QA Self-Test、Gate3 SchemaValidator、Gate5 评分
5. 用于 WORM 归档和复盘审计

### 9.2 CI 失败处理

| 失败步骤                  | 常见原因              | 处理方式                             |
| --------------------- | ----------------- | -------------------------------- |
| QA Self-Test          | YAML 语法错误、文件缺失    | 检查 `.ai/config/` 和 workflow YAML |
| Gate3 SchemaValidator | 文档参数↔代码常数不一致      | 同步文档或代码                          |
| Gate3.1 框架自审          | 权重和≠100%（BLOCKER） | 修复框架手册中的权重计算                     |
| Gate5 评分              | 实际检查发现问题          | 修复代码或确认 WARN 级别问题                |
| QA Gate               | 全部门禁汇总失败          | 逐项排查失败 Gate                      |

---

## 十、关键入口汇总

| 入口          | 链接                                                                 |
| ----------- | ------------------------------------------------------------------ |
| QA 系统仓库     | <https://github.com/linglong-quent/qa-system>                      |
| 量化项目仓库      | <https://github.com/linglong-quent/linglong>                       |
| 组织级工作流      | <https://github.com/linglong-quent/.github>                        |
| CI 运行日志     | <https://github.com/linglong-quent/qa-system/actions>              |
| 组织级 Actions | <https://github.com/organizations/linglong-quent/settings/actions> |

---

> **核心原则**：
>
> 1. 人定规则+审文档，AI 写代码，QA 拦截违规
> 2. linglong 只放业务代码，0 QA 逻辑残留；`qa_setup.py` 不向业务仓库复制代码
> 3. 一个 PR 一个变更，禁止多文件捆绑
> 4. CI 必须通过才能进 main；Gate3.1 权重错误阻断，其余 WARN
> 5. 紧急热更新必须 1 小时内补 Hotfix PR
> 6. 回测报告由 KUN 审核，金哥审批（不看代码）
> 7. 不产不良品，不漏不良品
