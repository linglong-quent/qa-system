# 部署 SOP

## 适用范围

玲珑量化 v4.0 生产环境部署与版本发布。开发阶段可简化，生产版严格执行。

## 前置条件

1. 代码已合入 main 分支，CI 全绿
2. 数据库迁移脚本已评审（DAT 负责）
3. 风控参数已双签（RGK + GOV）
4. 部署窗口已确认（避开盘中 9:25-15:00）

## 操作步骤

1. 拉取 main 最新代码：`git checkout main && git pull`
2. 安装依赖：`pip install -r requirements.txt`
3. 执行数据库迁移（如有）：`python scripts/migrate.py`
4. 运行冒烟测试：`pytest tests/smoke -q`
5. 重启服务：`docker compose up -d --build`
6. 健康检查：`curl http://localhost:8000/health`

## 验证方法

- 健康检查返回 200 且 `status=ok`
- 关键指标：行情延迟 < 3s，订单通道延迟 < 500ms
- 日志无 ERROR 级别异常

## 回滚方案

1. 切换到上一版本 tag：`git checkout <previous-tag>`
2. 回滚数据库迁移（如有）：`python scripts/migrate.py --down`
3. 重启服务并重新验证
4. 通知 GOV 和 OPS 记录事故
