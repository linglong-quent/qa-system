"""分析 BAN-5 高频数值，看哪些可以加入白名单"""
import json
import re
from collections import Counter

report_path = r"E:\WB\linglong\.ai\logs\qa-report.json"

with open(report_path, "r", encoding="utf-8") as f:
    report = json.load(f)

issues = report["checkers"]["code_ban"]["issues"]
ban5 = [i for i in issues if i.startswith("[BAN-5]")]

val_counter = Counter()
for issue in ban5:
    m = re.match(r'\[BAN-5\]\s+(.+?):(\d+)\s+魔法数字\s+(.+?)\s+->', issue)
    if m:
        val_counter[m.group(3)] += 1

print(f"BAN-5 总数: {len(ban5)}")
print(f"\nTop 50 高频数值:")
for val, cnt in val_counter.most_common(50):
    print(f"  {val:>15s}  {cnt:>4} 次")

# 分析：哪些可以加入白名单？
# - 252: 年化交易日 → 可以
# - 244: A股年交易日 → 可以  
# - 100, 100.0: 百分比基准 → 可以
# - 0, 1, -1: 已在白名单
# - 1000, 1024, 10000: 缓冲区/数量级 → 看情况
# - 70, 80, 60: 评分阈值 → 应配置化
# - 5, 10, 20, 60: 窗口参数 → 应配置化

print(f"\n=== 可加入白名单的候选（量化通用常数）===")
candidates = [
    ('252', '年化交易日'),
    ('244', 'A股年交易日'),
    ('250', '年交易日近似'),
    ('100', '百分比基准'),
    ('100.0', '百分比基准'),
    ('1000', '千分比/数量级'),
    ('10000', '万分之一/数量级'),
    ('1024', '2^10 缓冲区'),
    ('3600', '秒/小时'),
    ('86400', '秒/天'),
    ('365', '天/年'),
    ('0.01', '1% 基准'),
    ('0.001', '0.1% 基准'),
    ('100000000.0', '亿（市值单位）'),
    ('1000000', '百万'),
    ('500', '中证500/数量级'),
    ('300', '沪深300/数量级'),
    ('50', '百分比中位数'),
    ('200', '数量级/双百'),
]
for val, desc in candidates:
    cnt = val_counter.get(val, 0)
    if cnt > 0:
        print(f"  {val:>15s}  {cnt:>4} 次 - {desc}")
