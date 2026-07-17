# 案例：玲珑量化系统 — QA 防线落地全过程

> 本文展示玲珑量化交易系统如何从零到一组装 QA 防线。
> 作为 QA 系统的旗舰案例，证明这套独立框架在真实工程产品中的战斗力。

---

## 背景

玲珑量化系统是一个 A 股量化交易平台。代码量约 1.5 万行 Python，涵盖：
- 信号生成 → 风险控制 → 交易执行 三层架构
- 回测引擎、因子库、实盘网关
- CI/CD 流水线、每日全量回测

改造前状态：有零散的检查脚本（45 个 skill）、手动 Code Review、无统一 QA 框架。

---

## 第一步：引入 QA 系统核心（30 分钟）

```bash
# 1. 复制核心文件
cp -r <qa-system>/scripts/chk_*.py 项目/scripts/
cp -r <qa-system>/scripts/qa_check.py 项目/scripts/
cp <qa-system>/.pre-commit-config.yaml 项目/

# 2. 运行接入脚本
python scripts/qa_setup.py --project 项目/

# 3. 安装 pre-commit
cd 项目/
pre-commit install
pre-commit install --hook-type commit-msg
pip install pyyaml
```

**结果：** 7 个通用 checker 开箱即用，pre-commit 自动拦截不合规提交。

## 第二步：配置项目参数（15 分钟）

修改 `.ai/config/review-rules.yaml`，把 `scan_dirs` 指向玲珑的实际目录：

```yaml
inplace_check:
  scan_dirs: ["linglong/_core/", "linglong/strategy/"]
  severity: WARN

deadcode_check:
  scan_dirs: ["linglong/"]
  exempt_names: ["main", "__init__", "__all__"]
  entry_points: ["run_pipeline.py", "startup.py"]

lookahead_check:
  scan_dirs: ["linglong/backtest/", "linglong/strategy/"]
  severity: BLOCKER    # 回测前视偏差 → 零容忍
```

## 第三步：编写项目特有规则（按需）

玲珑特有的编码规范（CLAUDE.md 中的规则）挂到 `check(config, project_root)` 接口下：

```
.ai/plugins/
├── quantspec/iterrows_checker.py       ← 禁止 df.iterrows()
├── quantspec/magic_number_checker.py   ← 量化魔术数字检测
├── quantspec/cross_layer_import.py     ← 禁止 P0 层导入 P3 层
├── quantspec/hardcoded_market_data.py  ← 禁止硬编码行情路径
└── quantspec/constant_center.py        ← 常量必须来自 constants.py
```

每个文件写一个 `check()` 函数，QA 系统自动发现。

## 第四步：CI 集成（20 分钟）

在 `.github/workflows/ai-code-review.yml` 中：

```yaml
jobs:
  qa-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install pyyaml
      - run: python scripts/qa_check.py health    # 全部 checker 汇总
```

再加一条线：每日凌晨 2:00 全量扫描，趋势跟踪。

## 第五步：AI 编码约束（5 分钟）

把 `.ai/prompts/CLAUDE.md` 喂给 Cursor/Copilot：

> 将此文件作为 AI 编码助手的 system prompt，
> 确保每次 AI session 生成的代码从一开始就符合规范。

---

## 效果

| 指标 | 改造前 | 改造后 |
|------|--------|--------|
| 违规拦截时机 | 手动 Code Review | 提交前 pre-commit + CI 阻断 |
| 拦截覆盖率 | 模糊（靠人） | 7 通用 + N 项目 rule |
| 回测前视偏差 | 偶发，靠 Review 发现 | 自动检测，BLOCKER 级阻断 |
| 硬编码密钥 | 不定期扫描 | pre-commit 自动拦截 |
| 架构违规（跨层 import） | 无检查 | ImportBoundaryChecker 阻断 |
| 新人上手 | 学 45 个 skill | 学统一的 check() 接口 |

## 关键数字

- **QA 系统核心代码：** ~700 行（7 个 checker + 引擎）
- **玲珑项目特有插件：** 5 个文件，~200 行
- **安装时间：** 30 分钟完成基础接入
- **自检通过率：** 85/85 项测试通过
- **误报率：** 配置正确后为 0

## 经验

1. **通用层（Layer A）不要碰** — 升级时不会破坏项目特有规则
2. **项目层（Layer B）用 check() 接口** — 不必理解 HealthScorer 内部
3. **CI 层（Layer C）用 qa_check.py** — 统一入口，跨环境一致
4. **配置先严后松** — 先用 BLOCKER 跑一轮，再根据实际情况降级

---

> 玲珑量化系统是一个成功的工程产品案例。QA 系统的 7 个通用 checker
> 覆盖了 80% 的常见问题，剩余的 20% 由 5 个项目插件补充。
> 核心逻辑：QA 系统独立，项目规则插件化，双方互不污染。
