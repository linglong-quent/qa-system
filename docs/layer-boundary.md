# QA 系统三层架构边界定义

## Layer A — QA 系统核心（独立通用）

| 属性 | 值 |
|------|-----|
| 位置 | `D:\Users\pc\.kun\qa-system\` |
| 内容 | 19 个通用 checker + 引擎 + 门控 + 自检 |
| 污染 | **0 污染**。不进任何项目目录 |
| 升级 | 改一处，所有项目生效 |
| 依赖 | Python 3.12+、pyyaml |

这层和项目无关。不感知项目类型、不感知业务逻辑。

---

## Layer B — 项目补丁（项目特有规则）

| 属性 | 值 |
|------|-----|
| 位置 | 项目内 `.ai/plugins/` 或 `scripts/skill/` |
| 内容 | Generic checker 配置 + 项目特有 checker + 业务规则 |
| 污染 | **轻污染**。文件少，项目自有 |
| 升级 | 随项目独立迭代，不影响 Layer A |

**量化案例现状：**
- 19 个通用 checker 已从量化项目 skill 脚本反向提炼完成
- 确认真正量化特有：`future_leak`（回测未来泄露）
- 2 个 quantspec 插件（iterrows + magic_number）
- ci.yml 保留 15 个 skill 参考脚本（已完成的历史资产）

---

## Layer C — 产品集成（DevOps 流程）

| 属性 | 值 |
|------|-----|
| 位置 | 项目内 `.github/workflows/` + `.pre-commit-config.yaml` |
| 内容 | CI 触发条件、部署流程、文档构建、Issue 管理 |
| 污染 | **必然存在**。门控本身要求配置文件在项目内 |
| 3 个文件 | `.pre-commit-config.yaml` + 2 个 CI YAML（门控开关） |

这些文件是门控的物理存在——不是 QA 系统代码，是 QA 系统的"开关"。

---

## 边界原则

```
Layer A 不进入项目            → 0 污染 ✅
Layer B 不假设项目类型         → 配置化 ✅
Layer C 只含开关不含代码       → 最小污染 ✅
```

## 归属速查

| 资产 | 层 | 说明 |
|------|----|------|
| 19 个通用 checker | A | 独立 QA 系统 |
| pre-commit 引用 | C | 项目内开关 |
| CI YAML | C | 项目内开关 |
| .ai/plugins/quantspec/ | B | 量化特有插件 |
| ci.yml 15 个 skill | B | 量化历史资产 |
| future_leak | B | 回测特有 |
| ai-doc-build/generate/scan | C | 文档管线 |
| auto-assign | C | 开发流程 |
| 文档模板（mkdocs.yml） | B | 项目内容 |
