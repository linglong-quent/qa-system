#!/usr/bin/env python3
"""M51-(a) 门禁产出的消费者：把门禁结论投递到达人（复用 M24 通道，不另建）。

【为什么必须是被门禁自动调用，而不是一个"记得就跑"的脚本】
M51 四类同因之一是「规则存在却拦不住 / 无驱动」（`zeos_user`、`LinglongPGWriterCheck`）。
若本消费者只能手工执行，它自己就会变成第五个同类缺陷。故由 `qa_gate.py` 在
判定为 DENY 时**自动调用**本模块（默认开启，`--no-alert` 才关）。

【通道】复用 M24 的宿主侧告警桥 `linglong/ops/alert_bridge/alert_bridge.py`
（默认 http://127.0.0.1:9188），**不新建通道**。契约（M24 已立，本模块遵守）：
**HTTP 状态码是「是否真的送达」的唯一判据，绝不用 2xx 表示未送达。**

【为什么要区分 delivered / accepted】
- 桥返回 2xx ⇒ 真的送达 ⇒ delivered
- 桥返回非 2xx（503 未配置 / 500 投递失败）⇒ **未送达**，必须据此报错，
  绝不当成"已告警"。这正是 M24 负控的核心（received 会涨而 delivered 恒 0）。
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BRIDGE = os.environ.get("QA_ALERT_BRIDGE", "http://127.0.0.1:9188")
DEFAULT_TIMEOUT = float(os.environ.get("QA_ALERT_TIMEOUT", "10"))


def _post_alert(bridge: str, payload: dict, timeout: float) -> tuple:
    """投递到桥的 /api/v2/alerts（Alertmanager 兼容数组）。返回 (http_code, body, err)"""
    url = bridge.rstrip("/") + "/api/v2/alerts"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace") if hasattr(e, "read") else "", str(e)
    except Exception as e:
        return 0, "", str(e)


def _build_payload(contract: dict) -> dict:
    """从门禁契约构造告警。只取叶子字段，不序列化任何活对象。"""
    verdict = contract.get("verdict", "UNKNOWN")
    exit_code = contract.get("exit_code", -1)
    project = (contract.get("project") or {}).get("name", "?")
    summary = contract.get("summary") or {}
    failed_gates = [g.get("name") or g.get("gate_id")
                    for g in (contract.get("gates") or []) if g.get("passed") is False]
    blocking = [c.get("name") for c in (contract.get("checkers") or []) if c.get("blocking")]
    run_id = contract.get("run_id", "")
    src = contract.get("source_report") or {}

    detail = (
        f"verdict={verdict} exit={exit_code} 项目={project} run_id={run_id}\n"
        f"通过门禁 {summary.get('gates_passed')}/{summary.get('gates_total')}，"
        f"阻断级问题 {summary.get('tasks_blocking', 0)} 条\n"
        f"失败门禁: {', '.join([x for x in failed_gates if x]) or '无'}\n"
        f"阻断 checker: {', '.join([x for x in blocking if x]) or '无'}\n"
        f"裁决报告来源: {src.get('path', '?')}（source={src.get('source', '?')}）\n"
        f"契约: {contract.get('_contract_path', '(未记录)')}"
    )
    alert = {
        "labels": {
            "alertname": "QAGateDenied",
            "severity": "critical" if verdict == "DENY" else "warning",
            "project": project,
            "run_id": run_id or "",
            "source": "qa_gate",
        },
        "annotations": {
            "summary": f"QA 门禁 {verdict}（{project}）",
            "description": detail,
        },
        "startsAt": contract.get("generated_at", ""),
    }
    return {"version": "4", "status": "firing",
            "commonLabels": {"alertname": "QAGateDenied"},
            "alerts": [alert]}


def notify(contract: dict, bridge: str = "", timeout: float = 0,
           only_on_deny: bool = True) -> dict:
    """把门禁契约投递到达人。返回结构化结果（可安全写进契约 JSON）。

    返回字段：
      attempted / delivered / http_code / detail / bridge / suppressed
    `delivered` **只**在桥返回 2xx 时为 True —— 遵守 M24 契约。
    """
    bridge = bridge or DEFAULT_BRIDGE
    timeout = timeout or DEFAULT_TIMEOUT
    verdict = contract.get("verdict", "UNKNOWN")

    if only_on_deny and verdict not in ("DENY", "ERROR"):
        return {"attempted": False, "delivered": False, "suppressed": True,
                "http_code": 0, "bridge": bridge,
                "detail": f"verdict={verdict} 未达告警门槛（仅 DENY/ERROR 告警）"}

    payload = _build_payload(contract)
    code, body, err = _post_alert(bridge, payload, timeout)
    delivered = 200 <= code < 300
    detail = ("已送达" if delivered else "未送达") + f"（HTTP {code}）"
    if err:
        detail += f" err={err}"
    if body:
        detail += f" body={body[:200]}"
    return {"attempted": True, "delivered": delivered, "suppressed": False,
            "http_code": code, "bridge": bridge, "detail": detail}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="把门禁契约投递到达人（M24 通道）")
    p.add_argument("contract", help="qa_gate.py --json 产出的契约 JSON 路径")
    p.add_argument("--bridge", default="", help=f"告警桥地址（默认 {DEFAULT_BRIDGE}）")
    p.add_argument("--all", action="store_true", help="不限于 DENY，任何结论都投递")
    args = p.parse_args()

    contract = json.load(open(args.contract, encoding="utf-8-sig"))
    contract["_contract_path"] = os.path.abspath(args.contract)
    res = notify(contract, bridge=args.bridge, only_on_deny=not args.all)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # 退出码语义：未送达 ⇒ 1（让调用方无法把"没送到"当成成功）
    if res.get("attempted") and not res.get("delivered"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
