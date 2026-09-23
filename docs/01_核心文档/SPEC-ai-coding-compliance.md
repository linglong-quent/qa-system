# QA 系统 — 三层架构完整方案

> 一次落地，全链路闭环。
> Layer A: 通用引擎 | Layer B: 项目补丁 | Layer C: 产品集成

---

## 整体架构

```
Layer A — QA 引擎（通用框架，开箱即用）
├── 6 个内置 checker
│   ├── inplace_check      pandas inplace=True 检测
│   ├── lookahead_check    回测前视偏差
│   ├── secret_check       硬编码密钥
│   ├── deadcode_check     孤儿代码
│   ├── cyclic_check       循环导入
│   └── code_ban           通用禁用规则
├── HealthScorer（评分引擎 + 统一报告）
├── review-rules.yaml（评分 + ISO 25010 / NASA 权重）
├── secrets-scan.yaml / dead-code.yaml
├── pre-commit（black → isort → flake8 → mypy → 6 checker）
└── CI（PR 阻断 + 每日全量）

Layer B — 项目补丁（项目自己写，不污染框架）
├── .ai/plugins/        ← 自动发现，统一接口
│   └── quantspec/
│       ├── iterrows_checker.py     禁止 iterrows()
│       ├── magic_number_checker.py  量化魔法数字检测
│       └── ... 按需追加
├── review-rules.yaml 中 plugins 段控制启用/配置
├── HealthScorer 自动加载插件，结果归入同一份报告
└── _project_examples/ ← 参考模板（17 checker + 44 skill + 16 config）

Layer C — 产品集成（完整开发流程）
├── L1: CLAUDE.md        AI 指令约束 → 喂给 Cursor/Copilot
├── L2: pre-commit       提交前自动检查 + 拒绝
├── L3: CI/CD             PR 阻断 + 每日全量 + SARIF 导入
├── L4: 防错架构         脚手架 + 抽象层 → 从源头防错
└── metrics              趋势看板 + 30 天窗口追踪
```

## 配置文件结构

```
.ai/
├── config/
│   ├── review-rules.yaml    ← 核心：评分 + Layer A + Layer B 配置
│   ├── secrets-scan.yaml    ← 密钥扫描参数
│   ├── dead-code.yaml       ← 死代码扫描参数
│   ├── ai-pipeline.yaml     ← 流水线编排
│   ├── ai-whitelist.yaml    ← 白名单
│   └── arch-review.yaml     ← 架构审核
├── plugins/                 ← Layer B：项目特有 checker
│   ├── __init__.py
│   └── quantspec/
│       ├── iterrows_checker.py
│       └── magic_number_checker.py
├── prompts/
│   └── CLAUDE.md            ← Layer C：AI 指令约束
└── logs/
    └── qa-report.json       ← 运行结果

scripts/
├── chk_healthscorer.py      ← 核心引擎（A+B 加载）
├── chk_inplacechecker.py     ← 内置 checker
├── chk_lookaheadchecker.py
├── chk_secretchecker.py
├── chk_deadcodechecker.py
├── chk_cyclicchecker.py
├── chk_codebanchecker.py
├── chk_codeban_a.py / _b.py
├── chk_configauditchecker.py
├── chk_init_project.py
├── chk_load_yaml.py
└── chk_cli_*.py              ← CLI 接口
```

## 使用方式

### 1. 初始化项目
```bash
python scripts/chk_init_project.py
```

### 2. 本地检查
```bash
# pre-commit（推荐）
pre-commit install
pre-commit run --all-files

# 或手动运行
python -c "from chk_healthscorer import HealthScorer; s=HealthScorer('.'); r=s.run_all(); print(json.dumps(r, indent=2, ensure_ascii=False))"
```

### 3. CI 集成
- `ai-code-review.yml` — PR 时自动触发
- `ai-nightly-scan.yml` — 每日全量扫描

### 4. AI 编码约束
Cursor/Copilot 中引用 `.ai/prompts/CLAUDE.md` 作为 system prompt。

## 插件编写示例

```python
# .ai/plugins/quantspec/my_checker.py
CHECKER_ID = "plugin_quantspec_my_checker"
CHECKER_LABEL = "quant: 我的规则"

def check(config: dict, project_root: str) -> tuple[int, list[str]]:
    """统一接口: (errors, issues)"""
    errors = 0
    issues = []
    # 你的检测逻辑...
    return errors, issues
```

然后在 review-rules.yaml 中注册：
```yaml
plugins:
  enabled: true
  enabled_plugins:
    plugin_quantspec_my_checker: true
  plugin_configs:
    plugin_quantspec_my_checker:
      scan_dirs: ["src/"]
```

## 三层对应关系

| 层 | 负责 | 谁写 | 发布频率 |
|----|------|------|---------|
| A | 通用代码质量引擎 | QA 系统维护者 | 稳定版本 |
| B | 项目特有规则 | 项目组 | 随项目迭代 |
| C | 开发流程集成 | 项目组 / DevOps | 按需要 |

三个层各自独立。升级 A 不影响 B/C，改 B 不影响 A。
