# MAIN 分支 0 污染规则

> 对齐：GitHub 多智能体管理规范 V1.1 §2
> 标准依据：CMMI CM SP 1.3 / SLSA Level 2-3 / SOX 404

## 核心原则

**main 是纯净发布区。** 所有变更通过 CI+PR 管道进入。

```
feature 分支 ──→ CI ──→ PR ──→ main
 智能体自主   自动     人确认   发布
```

---

## 一、MAIN 上允许的 QA 资产

| 文件 | 行数 | 用途 | 标准依据 |
|------|------|------|---------|
| `.github/workflows/ai-code-review.yml` | ≤ 30 | PR 门控（preflight-gate） | CMMI VER SP 1.3 |
| `.github/workflows/ai-doc-scan.yml` | ≤ 30 | 文档扫描 | ISO 27001 A.8.10 |

这两个文件**只触发、不包含逻辑**。QA 系统在 CI runner 上 git clone 获取。

## 二、MAIN 上禁止的 QA 资产

| 资产 | 原因 | 标准依据 |
|------|------|---------|
| `.ai/` 任何目录 | QA 配置不进仓库 | CMMI CM SP 1.3 |
| `qa_*.py` / `chk_*.py` | QA 脚本不进仓库 | SLSA Level 2 |
| `.pre-commit-config.yaml` | 开发阶段工具 | — |
| `.cursorrules` / `copilot-instructions.md` | AI 工具配置 | — |
| CI 工作流中嵌入 QA 逻辑 | 只引用不内嵌 | SOX 职责分离 |

## 三、分支保护规则（GitHub 设置）

```bash
gh repo edit <org>/<repo> \
 --default-branch main \
 --enable-merge-commit \
 --delete-branch-on-merge

gh api repos/<org>/<repo>/branches/main/protection \
 -X PUT \
 -f required_status_checks='{"strict":true,"checks":[
 {"context":"lint"},
 {"context":"preflight-gate"},
 {"context":"test"}
 ]}' \
 -f enforce_admins=true \
 -f required_pull_request_reviews='{"required_approving_review_count":1}' \
 -f allow_force_pushes=false
```

QA 系统对应 checks：
- `lint` → ci.yml（量化特有 15 skill 检查器）
- `preflight-gate` → `qa_check.py health` + `qa_gate.py`
- `test` → ci.yml test job

## 四、智能体自检规则

QA 系统 `qa_gate.py` 中的 `Agent 权限边界` 门自动执行：

| 禁止行为 | QA 门控 | 标准依据 |
|---------|---------|---------|
| 直接 push main | GitHub 分支保护 | CMMI CM SP 1.3 |
| force push 任何分支 | GitHub 分支保护 | SLSA Level 2-3 |
| 跳过 CI 合并 PR | REQUIRED checks | Fagan 1976 / NASA 2002 |
| 同时改代码 + CI 规则 | Agent 权限边界门 | SOX 职责分离 |
| 自我审核自己 PR | GitHub 设置（1 人审核） | SOX / SOC 2 |
| 在 main 上开发 | 分支保护 | CMMI CM SP 1.3 |

## 五、分支命名（智能体自主选择）

| 前缀 | 用途 | 合并后 autodelete |
|------|------|:----------------:|
| `fix/*` | 修复 | ✅ |
| `feat/*` | 新功能 | ✅ |
| `docs/*` | 文档变更 | ✅ |
| `auto/*` | AI 自动修复 | ✅ |
| `chore/*` | 杂项维护 | ✅ |

## 六、工作流

```
Step 1: AI 创建 fix/xxx 分支（从 origin/main）
Step 2: 智能体开发 + 本地 commit
Step 3: git push（pre-commit 拦截违规）
Step 4: AI 自动提 PR
Step 5: CI 运行（lint + preflight-gate + test）
Step 6: CI 全绿 → 人审核 → AI 自动合并
Step 7: 自动删除分支
```

## 七、DEVELOP ONLY 文件

以下文件存在于 develop/feature 分支，但**不得合入 main**：

```
.github/workflows/ai-doc-build.yml     文档构建
.github/workflows/ai-doc-generate.yml  AI 文档生成
.github/workflows/ai-nightly-scan.yml  每日全量
.github/workflows/auto-assign.yml      Issue 分派
.github/workflows/ci.yml               量化特有检查
.ai/plugins/quantspec/                 量化插件
```

每个文件头部标注 `# MAIN-PROTECT: do not merge this file to main`。

---

> 参考：GitHub 多智能体管理规范 V1.1
> 标准矩阵：CMMI CM / CMMI VER / ISO 27001 / SOX / SLSA / NIST SP 800-53
