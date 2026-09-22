# QA 系统工具化分析 — 理论框架

> 核心问题：一个真正的 QA 工具需要什么要素？
> 不是"文件名是 .py 就是工具"。工具必须有 INPUT → PROCESS → OUTPUT → FEEDBACK。

---

## 一、工具的定义（来自软件工程与系统工程）

一个真正的工具，必须具备四条腿：

```
┌─────────────────────────────────────────────┐
│  1. TRIGGER（触发条件） — 什么让它跑？        │
│  2. RULES（规则输入）  — 按什么标准检查？      │
│  3. EXECUTION（执行逻辑）— 怎么检查？          │
│  4. ACTION（输出行为） — 发现问题后做什么？    │
│  5. FEEDBACK（反馈闭环）— 结果如何改进系统？   │
└─────────────────────────────────────────────┘
```

缺失任意一条，就不算完整的"工具"。

---

## 二、用这个标准审视当前系统

### 真工具（5条腿全齐）

| 文件 | TRIGGER | RULES | EXECUTION | ACTION | FEEDBACK |
|------|---------|-------|-----------|--------|----------|
| `qa_check.py health` | CI / 手动 | review-rules.yaml | HealthScorer.run_all() | exit 1 阻断 | 生成 qa-report.json |
| `pre-commit-config.yaml` | git commit | review-rules.yaml | 执行 checker | commit 拒绝 | 控制台输出 |
| `chk_secretchecker.py` | HealthScorer 调用 | 内置 + config | AST 扫描 .py | errors > 0 列问题 | issues 列表 |
| `qa_self_test.py` | 手动 | 自检清单 | 85 项检查 | exit 1 不通过 | 控制台报告 |

### 缺腿的工具

| 文件 | 缺什么 | 后果 |
|------|--------|------|
| `chk_cli_*.py` (5个) | 缺全部 | 0.2KB 空壳，不如没有 |
| `chk_configauditchecker.py` | 缺 TRIGGER | 没注册到 HealthScorer，永远不会跑 |
| `chk_init_project.py` | 缺 TRIGGER | qa_setup.py 重写了初始化，它成冗余 |
| `CLAUDE.md` | 缺 TRIGGER + ACTION | 写了但没人确保 AI 读了它 |

### 文档（只有描述，没有腿）

| 文件 | 它说了什么 | 它没做什么 |
|------|-----------|-----------|
| `docs/quality-gates.md` | G1-G15 质量门定义 | 没有任何 checker 实现"门"的逻辑 |
| `docs/case-study-linglong.md` | 集成步骤 | linglong_github 项目里还没跑过 |
| `10个 schema .json` | 定义数据结构 | 除了 qa-report.schema，其他从未被验证 |

---

## 三、行业标准对这个框架的要求

### IEEE 730 (软件质量保证计划)
- 质量活动必须可验证、可重复、可审计
- → 文档不算活动，脚本跑出的报告才算

### ISO 25010 (软件质量模型)
- 8 个质量维度需要对应的检查手段
- → 每个维度都必须有 TOOL 覆盖，不能只有描述

### CMMI Level 3 (定义级)
- 过程必须有定义、有度量、有反馈
- → 工具链必须是闭环：事前定义规则 → 事中检查 → 事后度量 → 改进规则

### NASA 8719.13 (软件安全)
- 每个安全规则必须有自动化检查
- → "禁止 eval" 写在 CLAUDE.md 里没用，必须 code_ban 实际拦截到

### NIST SP 800-53 (安全控制)
- 控制必须持续监控
- → 文档是一次性的，工具是持续运行的

---

## 四、AI 自治的视角

AI 编码助手（Cursor/Copilot）的 QA 流程和传统不同：

```
传统：
  人写代码 → 工具检查 → 人修复 → 人提交

AI 辅助：
  AI（读 CLAUDE.md）→ AI 生成代码 → 工具检查 → AI 读报告 → AI 自修复
```

这需要 CLAUDE.md 不只是一个文档，而是：
1. AI 编码时**必须加载**的约束
2. 约束内容的**正确性**能被工具验证
3. AI 生成的代码被 QA 工具检查后，**结果能喂回 AI** 指导修复

当前 CAUDE.md 只完成了第 1 步（写好了内容），第 2、3 步根本没有工具。

---

## 五、闭环模型：事前-事中-事后

### 应该长这样：

```
事前（Prevention）               事中（Detection）              事后（Correction）
─────────────────               ────────────────              ─────────────────
CLAUDE.md → AI 约束              pre-commit 拦截               QA Report 生成
规则配置 → 定义标准              CI 阻断违规                    Trend 追踪
脚手架 → 模板生成               schema 验证输出                反馈到事前规则
```

### 当前长这样：

```
事前：  CLAUDE.md（文档，不执行）
        review-rules.yaml（配置，执行于事中）

事中：  7个 checker ✅
        pre-commit 钩子 ✅
        CI 工作流 ✅
        Schema 验证（只 qa-report 一个）

事后：  qa-report.json（生成了但没被消费）
        无趋势追踪
        无反馈回路
        无质量门控
```

---

## 六、结论：系统需要什么

要让这个系统成为一个真正自洽的工具系统，需要：

1. **删除 16 个幽灵文件**（5 cli + 10 schema + 冗余 init_project）
2. **注册 configauditchecker 到 HealthScorer** → 多了 1 个真工具
3. **CLAUDE.md 工具化** → 加验证器检查 AI 是否真的遵守了规则
4. **质量门工具化** → G1-G15 用 YAML 定义，代码实现门禁逻辑
5. **QA Report 被消费** → 生成 HTML 看板或集成到 CI 可见位置
6. **反馈回路** → 历史报告对比，规则自动降噪

工具数量不是 34%（12/35 个文件），应该是 100%（没有文件不是工具）。
