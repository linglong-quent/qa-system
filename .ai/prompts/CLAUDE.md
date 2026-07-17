# QA System — AI 编码约束

你是 QA 系统的维护者。你修改一个 checker 前必须：
1. 跑 python scripts/qa_self_test.py（确保系统自检通过）
2. 跑 python scripts/qa_gate.py --report（确保门控不阻断）
3. 修改后必须更新 REVIEW-rules.yaml 中对应的配置段
4. 提交前必须通过 CI（qa-self-test check）
