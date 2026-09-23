import pathlib

p = pathlib.Path("scripts/qa_gate.py")
t = p.read_text(encoding='utf-8')

old = '''def main():
    import argparse
    parser = argparse.ArgumentParser(description="QA 总闸门 v4.1 — Gate0-Gate9 十层门禁（编排契约）")
    parser.add_argument("--report", "-r", action="store_true", help="只报告不阻断（恒 exit 0）")
    parser.add_argument("--gate", "-g", type=str, default="",
                        help="仅运行指定 gate (如 --gate=3)")
    parser.add_argument("--project", "-p", type=str, default="",
                        help="目标项目根目录")
    parser.add_argument("--json", type=str, default="",
                        help="输出结构化门禁契约 JSON 到该路径（编排系统消费）")
    parser.add_argument("--run-id", type=str, default="",
                        help="运行标识：产物隔离到 {base}/.ai/runs/{run_id}/")
    parser.add_argument("--runs-dir", type=str, default="",
                        help="run 基准目录（默认 QA_SYSTEM_ROOT/.ai/runs）")
    parser.add_argument("--allow-production-bypass", action="store_true",
                        help="显式允许生产旁路（否则 QA_ENV=production 不再放行门禁）")
    parser.add_argument("--readonly", action="store_true",
                        help="只读审计：禁止写不良品登记与被审对象的 CB 收件箱（反向检验/审计用）")
    parser.add_argument("--allow-stale-report", action="store_true",
                        help="M51-①：显式允许以非本 run 的存量报告下结论"
                             "（否则裁决对象必须来自 {run_dir}/qa-report.json）")
    parser.add_argument("--no-alert", action="store_true",
                        help="M51-(a)：强制关闭告警投递（关闭原因会记入契约 alerts.detail）")
    parser.add_argument("--alert", action="store_true",
                        help="M51-(a)：把 DENY 结论告警到达人（走 M24 告警桥，不另建通道）。"
                             "QA_ENV=ci 时自动开启；--readonly 审计模式强制关闭（审计不得有外部副作用）")
    args = parser.parse_args()'''

new = '''def _build_argparser():
    """构建 CLI 参数解析器"""
    import argparse
    parser = argparse.ArgumentParser(description="QA 总闸门 v4.1 — Gate0-Gate9 十层门禁（编排契约）")
    parser.add_argument("--report", "-r", action="store_true", help="只报告不阻断（恒 exit 0）")
    parser.add_argument("--gate", "-g", type=str, default="",
                        help="仅运行指定 gate (如 --gate=3)")
    parser.add_argument("--project", "-p", type=str, default="",
                        help="目标项目根目录")
    parser.add_argument("--json", type=str, default="",
                        help="输出结构化门禁契约 JSON 到该路径（编排系统消费）")
    parser.add_argument("--run-id", type=str, default="",
                        help="运行标识：产物隔离到 {base}/.ai/runs/{run_id}/")
    parser.add_argument("--runs-dir", type=str, default="",
                        help="run 基准目录（默认 QA_SYSTEM_ROOT/.ai/runs）")
    parser.add_argument("--allow-production-bypass", action="store_true",
                        help="显式允许生产旁路（否则 QA_ENV=production 不再放行门禁）")
    parser.add_argument("--readonly", action="store_true",
                        help="只读审计：禁止写不良品登记与被审对象的 CB 收件箱（反向检验/审计用）")
    parser.add_argument("--allow-stale-report", action="store_true",
                        help="M51-①：显式允许以非本 run 的存量报告下结论"
                             "（否则裁决对象必须来自 {run_dir}/qa-report.json）")
    parser.add_argument("--no-alert", action="store_true",
                        help="M51-(a)：强制关闭告警投递（关闭原因会记入契约 alerts.detail）")
    parser.add_argument("--alert", action="store_true",
                        help="M51-(a)：把 DENY 结论告警到达人（走 M24 告警桥，不另建通道）。"
                             "QA_ENV=ci 时自动开启；--readonly 审计模式强制关闭（审计不得有外部副作用）")
    return parser


def main():
    parser = _build_argparser()
    args = parser.parse_args()'''

assert old in t
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("extracted _build_argparser() from main() — main() now ~175 lines")
