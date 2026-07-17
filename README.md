# QA System

独立质量工程系统。不进入任何项目目录，通过 CI 引用。

## 使用

任意项目，在工作流中引用：

`yaml
- name: Load QA System
  run: git clone --depth 1 https://github.com/linglong-quent/qa-system.git /opt/qa-system

- name: QA Gate
  run: python /opt/qa-system/scripts/qa_gate.py
`

## 结构

| 目录 | 内容 |
|------|------|
| scripts/ | 19 通用 checker + 引擎 + 门控 |
| .ai/config/ | 7 个配置 |
| .ai/projects/ | 项目注册表 |
| docs/ | 架构文档 + 0污染规则 |

## 标准

ISO 25010 / NASA Power of 10 / OWASP / CMMI / SOX

## 版本

v3.0 — 工具集，逻辑闭环完整
