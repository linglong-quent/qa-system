# 量化交易系统代码标准 v1.0

> 基于 ISO 25010 + NASA Power of 10 + OWASP + 量化行业最佳实践
> 适用范围：linglong 玲珑量化交易系统
> 生效日期：2026-07-25

---

## 一、架构标准

### 1.1 分层架构（Domain-Driven Design）

```
┌─────────────────────────────────────────┐
│  access 层 (接入层)                    │  LLM/API/UI 接入，零业务逻辑
├─────────────────────────────────────────┤
│  cognition 层 (认知层)                  │  画像/评分/博弈，纯计算无副作用
├─────────────────────────────────────────┤
│  decision 层 (决策层)                   │  仓位/风控/轮动，核心业务逻辑
├─────────────────────────────────────────┤
│  factor 层 (因子层)                     │  因子计算/特征工程，纯函数
├─────────────────────────────────────────┤
│  data 层 (数据层)                       │  数据源/缓存/持久化，唯一 IO 入口
├─────────────────────────────────────────┤
│  shared 层 (共享层)                     │  工具/类型/常量，无业务依赖
└─────────────────────────────────────────┘
```

**边界规则（强制执行）：**

| 调用方向 | 允许？ | 示例 |
|---------|--------|------|
| 上层 → 下层 | ✅ | decision → data |
| 下层 → 上层 | ❌ | data → decision |
| 同层 → 同层 | ⚠️ 仅限 API | factor → factor.api |
| 跨层跳跃 | ❌ | decision → sqlite3 |

**BAN-1 / BAN-2 违规即阻断 PR。**

---

### 1.2 模块化与热插拔标准

#### 模块设计原则

| 原则 | 说明 | 对应标准 |
|------|------|---------|
| **单一职责** | 一个模块只做一件事 | ISO 可维护性 |
| **接口隔离** | 只暴露必要的 API | ISO 可移植性 |
| **依赖倒置** | 上层依赖抽象，不依赖具体 | SOLID |
| **开闭原则** | 对扩展开放，对修改关闭 | SOLID |

#### 热插拔架构模式

```python
# ✅ 标准：插件式因子注册
FACTORY_REGISTRY = {}

def register_factor(name: str):
    """因子装饰器注册 — 新增因子不需要改工厂代码"""
    def decorator(cls):
        FACTORY_REGISTRY[name] = cls
        return cls
    return decorator

# 新增因子只需：
@register_factor("rsi")
class RSIFactor(BaseFactor):
    pass
```

| 模式 | 适用场景 | 速度影响 |
|------|---------|---------|
| 装饰器注册 | 因子/策略/信号源 | 启动时注册，运行时 0 开销 |
| 配置驱动 | 数据源/适配器 | 首次加载略慢，运行时快 |
| 入口函数 | 检查器/门禁 | 列表遍历，线性开销 |

#### 模块化检查清单

- [ ] 模块通过 `__init__.py` 暴露 API，不暴露内部实现
- [ ] 新增功能通过注册机制（装饰器/配置）注册，不修改工厂代码
- [ ] 模块间通过接口（interface/抽象类）定义契约
- [ ] 可独立禁用模块有 on/off 开关
- [ ] 替换实现不影响调用方代码

---

### 1.3 性能标准（量化特有 — 速度第一）

#### 延迟预算（Latency Budget）

| 阶段 | 目标 | 警告 | 严重 | 对应标准 |
|------|------|------|------|---------|
| 行情拉取 | 200ms | 500ms | 1000ms | ISO 性能效率 |
| 因子计算 | 100ms | 300ms | 500ms | ISO 性能效率 |
| 信号生成 | 50ms | 150ms | 300ms | ISO 性能效率 |
| 风控检查 | < 50ms | 100ms | 200ms | NASA-5 快速失败 |
| 订单发送 | < 30ms | 50ms | 100ms | ISO 性能效率 |

#### 性能优化优先级（量化特有）

| 优先级 | 优化手段 | 适用场景 |
|--------|---------|---------|
| P0 | 向量化（numpy/pandas） | 因子计算、批量处理 |
| P0 | 预计算 + 缓存 | 常用因子、画像结果 |
| P1 | 内存数据库（SQLite 内存库） | 实时数据查询 |
| P1 | 批量接口（避免 N+1 查询） | 多股票数据加载 |
| P2 | 异步/并发 | IO 密集型（多数据源拉取） |
| P2 | 懒加载 | 不常用的大模块 |

#### 性能红线（必须遵守）

```python
# ❌ 禁止：循环中做 IO
for stock in stock_list:
    df = pd.read_sql(f"SELECT * FROM {stock}")  # N+1 查询

# ✅ 标准：批量加载
df_all = load_batch(stock_list)
```

| 禁止模式 | 替代方案 |
|---------|---------|
| pandas iterrows / itertuples | 向量化操作 / apply |
| 循环内数据库查询 | 批量查询 + 内存处理 |
| 重复计算相同因子 | 缓存 + 预计算 |
| 全表扫描 | 索引 + 分区 |

---

## 二、编码标准

### 2.1 NASA Power of 10（安全编码十大规则）

| # | 规则 | 对应 BAN | 说明 |
|---|------|----------|------|
| 1 | 简化控制流 — 循环不超过 2 层嵌套 | - | 超过 2 层必须拆分函数 |
| 2 | 所有循环必须有明确的上界 | - | 防止死循环 |
| 3 | 初始化后只读 — 命名常量 | **BAN-5** | 魔法数字必须有名字 |
| 4 | 函数单一职责 — 不超过 60 行 | **BAN-11** | 大函数必须拆分 |
| 5 | 快速失败 — 断言前置检查 | - | 入口处验证所有前提 |
| 6 | 变量最小作用域 | - | 尽量局部变量 |
| 7 | 检查返回值 | - | 不忽略错误返回 |
| 8 | 异常处理要有限制 | **BAN-6** | 禁止 except: pass |
| 9 | 输入必须限制 | - | 输入长度/范围校验 |
| 10 | 编译时/静态检查 | - | lint + 类型标注 |

---

### 2.2 代码风格标准（PEP 8 + ISO 25010 可维护性）

> **强制执行**：所有 STYLE 规则纳入 Gate5 阻断级检查，违规即阻断 PR。

#### STYLE-01 文件命名（PEP 8 — 模块命名）

| 类型 | 规则 | 示例 |
|------|------|------|
| 模块/文件 | 全小写 + 下划线 | `data_service.py`, `risk_engine.py` |
| 类 | 大驼峰（PascalCase） | `DataService`, `RiskEngine` |
| 函数/方法 | 全小写 + 下划线 | `load_data()`, `calculate_risk()` |
| 常量 | 全大写 + 下划线 | `MAX_RETRY`, `DEFAULT_TIMEOUT` |
| 变量 | 全小写 + 下划线 | `stock_list`, `daily_return` |

```python
# ❌ 禁止：大驼峰文件名
DataService.py
riskEngine.py

# ❌ 禁止：混合命名风格
def CalculateRisk():        # 函数用了 PascalCase
class data_service:         # 类用了 snake_case

# ✅ 标准
class DataService:
    def load_data(self) -> pd.DataFrame:
        MAX_RETRY = 3
        stock_list = []
```

---

#### STYLE-02 行长度（PEP 8 — 最大行宽）

| 规则 | 限制 | 说明 |
|------|------|------|
| 单行长度 | **≤ 120 字符** | 超过必须换行 |
| 缩进对齐 | 4 空格 | 不用 Tab |
| 续行缩进 | 悬挂缩进或对齐括号 | 避免反斜杠续行 |

```python
# ❌ 禁止：超长行
result = calculate_complex_factor(dataframe, window_size, shift_period, smooth_alpha, benchmark_code, risk_free_rate, transaction_cost)

# ✅ 标准：括号内换行（悬挂缩进）
result = calculate_complex_factor(
    dataframe,
    window_size,
    shift_period,
    smooth_alpha,
    benchmark_code,
    risk_free_rate,
    transaction_cost,
)

# ✅ 标准：长条件换行
if (price > upper_band
        and volume > volume_threshold
        and rsi > overbought_level):
    trigger_sell_signal()
```

---

#### STYLE-03 命名规范（PEP 8 — 描述性命名）

| 元素 | 风格 | 反例 | 正例 |
|------|------|------|------|
| 函数 | snake_case + 动词开头 | `proc()`, `data()`, `calc()` | `process_signal()`, `load_market_data()` |
| 类 | PascalCase + 名词 | `dataservice`, `Risk_Engine` | `DataService`, `RiskEngine` |
| 变量 | snake_case + 描述性 | `x`, `tmp`, `foo`, `val1` | `stock_code`, `daily_return`, `position_size` |
| 布尔变量 | is/has/can/should 前缀 | `flag`, `check`, `status` | `is_trading_day`, `has_position`, `can_open_position` |
| 私有方法 | _ 单下划线前缀 | `__calc()`, `internal_do()` | `_calculate_position()`, `_validate_input()` |

```python
# ❌ 禁止：无意义缩写
def proc(df, n, p):
    x = df['close'].rolling(n).mean()
    return x > p

# ✅ 标准：描述性命名
def calculate_moving_average_crossover(
    price_data: pd.DataFrame,
    short_window: int,
    long_window: int,
) -> pd.Series:
    short_ma = price_data["close"].rolling(short_window).mean()
    long_ma = price_data["close"].rolling(long_window).mean()
    return short_ma > long_ma
```

---

#### STYLE-03b 跨域命名空间隔离 & 单一数据源（强制）

> **来源**: 玲珑 v4.0 同名类冲突事故复盘（2026-07）
> **级别**: 🚫 BLOCKER — 违反即阻断合并

**根因**: PEP 8 仅规定命名风格（PascalCase/snake_case），未规定跨域同名隔离。导致多域并行开发时出现 `MarketState` / `FactorICResult` / `FusionResult` 等同名类，字段不一、语义不一，运行时不报错但行为冲突。

##### 原则1: 跨域类名必须加"域前缀"或"领域修饰词"

| 通用名 (禁止跨域) | 域前缀方案 |
|------------------|-----------|
| `MarketState` | `QuadrantMarketState` (factor域) / `RegimeMarketState` (decision域) |
| `FusionResult` | `FactorFusionResult` (factor) / `SignalFusionResult` (cognition) / `DataFusionResult` (data) |
| `CapitalFlowResult` | `PortraitCapitalFlowResult` (cognition-portrait) |
| `CircuitBreakerState` | `PositionRiskState` (cognition-portrait — 仓位风险状态机) |
| `CircuitBreakerResult` | `PortfolioCircuitBreakerResult` (decision — 组合熔断结果) |
| `Signal` | `RotationSignal` (scripts) / `NormalizedSignal` (cognition-normalization) |

**判定规则**:
1. 类名命中以下通用词时强制加域前缀: `Result` / `State` / `Status` / `Signal` / `Config` / `Engine` / `Manager`
2. 域前缀优先级: 子域 > 大域 > 模块 (如 `PortraitCapitalFlowResult` 而非 `CognitionCapitalFlowResult`)
3. scripts / ops / tests 等非 domain 路径必须加路径前缀避免与 domain 同名

##### 原则2: 单一数据源 (Single Source of Truth, SSOT)

| 资产类型 | 唯一来源 | 禁止行为 |
|---------|---------|---------|
| `PROJECT_ROOT` 常量 | `shared/data_paths.py` | 在其他模块 `Path(__file__).resolve().parent.parent` |
| `SCORING` 评分阈值 | `shared/scoring_thresholds.py` | 在 `*_config.py` 中重复定义 SCORING dict |
| `FactorICResult` 类 | `backtest/engines/factor_ic_analysis.py` (10字段完整版) | 在 `backtest_models.py` 重新定义简化版 |
| 健康检查入口 | `ops/scripts/l7_health_check.py` | 同时存在 `health_check.py` / `disk_health.py` |
| 熔断器实现 | `shared/resilience.py` | `shared/circuit_breaker.py` 软转发 |
| 异常基类 | `shared/exceptions.py` | domain 各引擎自定义异常基类 |

##### 原则3: 禁止软转发 / 别名 / 纯转发模块

```python
# ❌ 禁止: 软转发别名 (新系统不允许打补丁)
EventBus = MemoryEventBus  # 删, 直接用 MemoryEventBus
MarketRegime = MacroRegimeAdapter  # 删, 直接用 MacroRegimeAdapter
from x import y as z  # 仅在解决命名冲突时允许, 否则直接用原名

# ❌ 禁止: 纯转发模块 (新系统不允许)
# shared/circuit_breaker.py 内容仅为 "from shared.resilience import *" — 整文件删除

# ✅ 标准: 直接引用, 不打补丁
from shared.event_bus import MemoryEventBus
from shared.resilience import CircuitBreaker, retry_with_backoff
```

##### 原则4: 命名冲突静态校验 (CI 强制)

| 检查项 | 工具 | 触发条件 |
|-------|------|---------|
| 同名类跨文件冲突 | `ast` 扫描 | 两个 `*.py` 文件定义同名 `class` 且字段不同 |
| 软转发别名 | AST BinOp/Eq 检测 | `X = Y` 形式且 Y 是已导入的类名 |
| 重复常量定义 | grep + import graph | 同名常量在多个模块 `=` 定义, 未通过 import 复用 |
| 纯转发模块 | import graph 分析 | 模块体仅含 `from X import *` / `Y = X` 等转发语句 |

##### 处置流程

1. **发现冲突**: 静态扫描报告 → 列入 DEFECTS_AND_IMPROVEMENTS.md
2. **判定归属**: 按"域前缀方案"重命名, 字段更完整者保留为单一数据源
3. **删除冗余**: 旧定义直接删除, 不留软转发/别名/废弃标记 (新系统未上线)
4. **更新引用**: 测试代码、文档、CODE_WIKI.md 同步更新
5. **回归验证**: 全测试套件 + QA-SYS 11 门禁全通过

---

#### STYLE-04 日志格式（12-Factor — 结构化日志）

| 规则 | 说明 |
|------|------|
| **禁止 f-string** | 日志消息用 `%` 格式化，延迟求值 |
| 日志级别 | debug/info/warning/error/critical 五级 |
| 结构化字段 | 关键字段（symbol、strategy、order_id）必须出现在消息中 |

```python
# ❌ 禁止：f-string 日志（每次都求值，性能浪费）
logger.info(f"订单成交: {order_id} 价格={price} 数量={quantity}")

# ✅ 标准：% 格式化 + 延迟求值
logger.info("订单成交: order_id=%s price=%.2f qty=%d", order_id, price, quantity)

# ✅ 标准：结构化日志推荐
logger.info(
    "订单成交: order_id=%s symbol=%s price=%.2f qty=%d side=%s",
    order_id, symbol, price, quantity, side,
)
```

---

#### STYLE-05 文件行数（ISO 25010 可维护性）

| 阈值 | 限制 | 说明 |
|------|------|------|
| **单文件最大行数** | **500 行** | 超过必须拆分模块 |
| 理想范围 | 100-300 行 | 单一职责，便于理解 |

**拆分原则：**
1. 按职责拆分：数据加载 / 计算逻辑 / 结果输出 分离
2. 按抽象层级拆分：高层接口 / 底层实现 分离
3. 按领域拆分：不同业务领域放不同模块

```
# ❌ 禁止：单文件 900 行
data_service.py  # 900 行，包含数据加载/缓存/计算/存储

# ✅ 标准：按职责拆分
data_service/
├── __init__.py
├── api.py              # 对外接口
├── loader.py           # 数据加载
├── cache.py            # 缓存管理
├── processor.py        # 数据处理
└── storage.py          # 持久化存储
```

---

#### STYLE-06 函数行数（NASA Power of 10 规则 4）

| 阈值 | 限制 | 说明 |
|------|------|------|
| **函数最大行数** | **60 行** | 超过必须拆分（不含空行和注释） |
| 理想范围 | 5-30 行 | 单一职责，一眼看完 |

**拆分方法：**
1. 提取子函数：把逻辑块提取为有意义的子函数
2. 早期返回：减少嵌套层级
3. Guard Clause：前置条件检查提前返回

```python
# ❌ 禁止：100+ 行的巨型函数
def process_portfolio(data):
    # 30行：数据清洗
    ...
    # 20行：计算收益
    ...
    # 25行：风控检查
    ...
    # 20行：生成报告
    ...
    # 总计：95 行

# ✅ 标准：拆分为小函数，顶层函数像目录
def process_portfolio(data: PortfolioData) -> PortfolioResult:
    cleaned_data = _clean_data(data)
    returns = _calculate_returns(cleaned_data)
    risk_report = _check_risk_limits(returns)
    return _generate_report(returns, risk_report)
```

---

### 2.3 魔法数字标准（BAN-5 详细分类）

#### L1 系统级常量 — 不算魔法数字

| 类型 | 示例 | 处理方式 |
|------|------|---------|
| 0, 1, -1 | `i=0`, `idx += 1` | 约定俗成，白名单 |
| 数学常数 | PI, E, sqrt(2) | `math.pi`，不算 |
| 单位换算 | `* 100`（百分比） | 命名常量或接受为惯例 |
| 交易日 | 252（年化交易日） | 领域常量 |

#### L2 基础设施配置 — 必须配置化

| 类型 | 示例 | 存放位置 |
|------|------|---------|
| 数据源 IP/端口 | TDX HOST/PORT | `data_config.py` |
| 数据库路径 | DB_PATH | `data_config.py` |
| 超时/重试 | timeout, retry | `data_config.py` |
| 缓存大小 | buffer_size | `data_config.py` |

#### L3 领域业务参数 — 必须配置化

| 领域 | 示例 | 存放位置 |
|------|------|---------|
| 因子窗口 | MA(5, 10, 20, 60) | `factor_config.py` |
| 评分阈值 | 70分良好, 80分优秀 | `decision_config.py` |
| 风控阈值 | 止损-15%, 回撤-7% | `decision_config.py` |
| 仓位系数 | Kelly 0.5, ADR 1.2 | `decision_config.py` |
| 画像参数 | 周期/权重/分级 | `portrait_config.py` |

#### L4 策略参数 — 配置文件/数据库

| 类型 | 示例 | 存放位置 |
|------|------|---------|
| 策略调优参数 | 持仓周期、止盈比例 | 策略配置 + 回测优化 |
| 选股参数 | 市值范围、流动性 | 选股配置 |

#### L5 运行时变量 — 不算魔法数字

| 类型 | 示例 | 说明 |
|------|------|------|
| 循环计数器 | `for i in range(5)` | 局部变量 |
| 临时累加器 | `count = 0` | 函数内 |
| 索引/偏移 | `idx = 0` | 函数内 |

#### 配置化标准写法

```python
# ✅ 标准：领域配置字典 + 环境变量覆盖
RISK = {
    "hard_stop_loss": float(os.environ.get("LINGLONG_RISK_HARD_STOP", "-0.15")),
    "max_drawdown": float(os.environ.get("LINGLONG_RISK_MAX_DD", "-0.15")),
    "per_stock_cap": float(os.environ.get("LINGLONG_RISK_PER_STOCK_CAP", "0.25")),
}

# ✅ 标准：调用方语义清晰
if drawdown < RISK["hard_stop_loss"]:
    trigger_hard_stop()

# ❌ 禁止：硬编码
if drawdown < -0.15:
    trigger_hard_stop()
```

---

### 2.4 异常处理标准（BAN-6）

```python
# ❌ 禁止：空 except
try:
    do_something()
except:
    pass

# ✅ 标准：捕获具体异常 + 日志
try:
    do_something()
except ValueError as e:
    logger.debug(f"计算失败: {e}")
    return default_value
```

| 场景 | 处理方式 | 对应标准 |
|------|---------|---------|
| 数据缺失 (NaN) | 返回默认值 + debug 日志 | ISO 可靠性 |
| 网络超时 | 重试 + 降级 | NASA-8 |
| 参数非法 | 快速失败 + 明确错误 | NASA-5 |
| 数据库错误 | 回滚 + 告警 | OWASP A03 |

---

### 2.5 安全编码标准（OWASP Top 10 映射）

| OWASP | 对应 BAN | 说明 |
|-------|----------|------|
| A01 访问控制失效 | BAN-1 / BAN-2 | 分层边界违规 |
| A03 注入 | BAN-9 | 裸 DB 连接 |
| A03 注入 | BAN-8 | eval/exec |
| A07 认证失效 | BAN-7 | 硬编码 IP |
| A09 安全日志 | BAN-12 | 日志结构 |

---

### 2.6 可靠性与熔断标准（Release It! 稳定性模式）

> **强制执行**：所有外部网络调用必须满足三级保护要求。

#### 三级保护模型

| 级别 | 要求 | FUSE 代码 | 严重程度 |
|------|------|-----------|---------|
| **L1 基础** | try/except + timeout | FUSE-001 | 🔴 阻断 |
| **L2 重试** | 指数退避重试（至少 3 次） | FUSE-002 | 🟡 警告 |
| **L3 熔断** | 熔断器（Circuit Breaker） | FUSE-003 | 🟢 建议 |

#### L1 基础要求（阻断级）

所有外部调用**必须**：
1. 包裹在 `try/except` 中，捕获网络异常
2. 设置明确的 `timeout` 参数，禁止永不超时
3. 异常时记录结构化日志（包含 endpoint、耗时、错误类型）

```python
# ❌ 禁止：无任何保护
def fetch_price(code: str) -> dict:
    resp = requests.get(f"https://api.example.com/price/{code}")
    return resp.json()

# ✅ L1 标准：try/except + timeout + 日志
def fetch_price(code: str) -> dict | None:
    try:
        resp = requests.get(
            f"https://api.example.com/price/{code}",
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        logger.warning("价格查询超时: code=%s", code)
        return None
    except requests.RequestException as e:
        logger.error("价格查询失败: code=%s error=%s", code, e)
        return None
```

#### L2 重试要求（警告级）

关键路径外部调用**应该**：
1. 使用指数退避重试（推荐 `tenacity` 库）
2. 重试次数 ≥ 3 次
3. 只对幂等操作重试，非幂等操作谨慎

```python
# ✅ L2 标准：tenacity 指数退避重试
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def fetch_price_with_retry(code: str) -> dict:
    resp = requests.get(f"https://api.example.com/price/{code}", timeout=5)
    resp.raise_for_status()
    return resp.json()
```

#### L3 熔断要求（建议级）

高频外部调用**建议**：
1. 集成熔断器模式（三态：CLOSED → OPEN → HALF_OPEN）
2. 错误率超过阈值时自动熔断
3. 熔断期间快速失败，保护下游系统

```python
# ✅ L3 标准：Circuit Breaker
from shared.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

@breaker
def fetch_market_data(symbol: str) -> pd.DataFrame:
    resp = requests.get(f"https://api.example.com/data/{symbol}", timeout=10)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())
```

#### 外部调用类型清单

以下类型的调用必须满足至少 L1 标准：

| 类型 | 示例库 | 量化场景 |
|------|--------|---------|
| HTTP 请求 | requests, httpx, aiohttp | 行情 API、新闻 API、第三方数据 |
| WebSocket | websocket, websockets | 实时行情推送 |
| 数据库连接 | pymongo, redis, psycopg2 | 行情数据库、缓存层 |
| Socket 通信 | socket | 交易柜台、行情网关 |
| 消息队列 | pika, kafka | 事件驱动、订单路由 |

---

## 三、配置管理标准

### 3.1 配置分层

| 层级 | 内容 | 存放位置 | 环境变量覆盖 | 修改频率 |
|------|------|---------|-------------|---------|
| L1 系统常量 | 数学常数、单位换算 | shared/ 顶层常量 | ❌ | 永不变 |
| L2 基础设施 | 数据源、数据库、路径 | domain/data/data_config.py | ✅ | 极少 |
| L3 领域参数 | 因子窗口、风控阈值 | domain/*/config.py | ✅ | 偶尔 |
| L4 策略参数 | 策略调优参数 | 策略配置文件 | ✅ | 经常 |
| L5 运行时 | 计算中间值 | 函数局部 | ❌ | 每次 |

### 3.2 配置文件规范

```python
# ✅ 标准写法
# domain/decision/decision_config.py

from __future__ import annotations
import os

SCORING = {
    "excellent": int(os.environ.get("LINGLONG_SCORE_EXCELLENT", "80")),
    "good": int(os.environ.get("LINGLONG_SCORE_GOOD", "70")),
}

RISK = {
    "hard_stop_loss": float(os.environ.get("LINGLONG_RISK_HARD_STOP", "-0.15")),
}

__all__ = ["SCORING", "RISK"]
```

**命名约定：
- 配置字典：全大写下划线
- 环境变量：`LINGLONG_领域_参数名`
- 配置文件：`*_config.py`

### 3.3 参数与配置管理分类细则（量化 A++ 行业标准）

> **强制执行**：所有魔法数字（BAN-5）必须按本节分类归位，违反即阻断 PR。

#### 五层参数分类体系（对标微软 Qlib 声明式配置）

| 层级 | 定义 | 存放位置 | 环境变量覆盖 | 示例 |
|------|------|---------|-------------|------|
| **L1 系统级常量** | 物理常数、数学常数、单位换算 | 代码顶部命名常量 | ❌ | `SQRT_252 = 15.87` |
| **L2 基础设施配置** | 数据源、数据库、路径、端口 | `data_config.py` | ✅ | `TDX_HOST`, `DB_PATH` |
| **L3 领域业务参数** | 因子窗口、阈值、权重、评分规则 | 各领域 `*_config.py` | ✅ | `MA_WINDOWS`, `RSI_THRESHOLD` |
| **L4 策略参数** | 具体策略的调优参数 | `config/*.yaml` | ✅ | `stop_loss`, `take_profit` |
| **L5 运行时变量** | 计算中间值、循环计数器 | 函数局部变量 | ❌ | `for i in range(3)` |

#### BAN-5 魔法数字场景分类处理标准

| 数字类型 | 行业标准处理 | 判定依据 |
|---------|-------------|---------|
| `0, 1, -1` | 约定俗成的例外，白名单豁免 | 逻辑值/索引基准 |
| 单位换算（`*100, /100, /252`） | 命名常量或接受为惯例 | 换算系数 |
| 因子窗口参数（`5, 10, 20, 60` 日） | L3 领域配置字典 | 业务语义参数 |
| 风控阈值（止损、回撤、仓位上限） | L3 风控配置模块 + 环境变量 | 可调参数 |
| 数据源 IP/端口 | L2 基础设施配置 + 环境变量 | 部署参数 |
| 循环范围（`range(3), range(5)`） | 函数内小范围可接受 | 局部计数器 |
| 字典/配置表中的值 | 配置本身就是命名 | 数据定义 |
| 关键字参数（`func(period=20)`） | 调用处已语义化 | 已命名参数 |
| 常量表（列表/元组中的枚举值） | 数据定义，非魔法 | 枚举值 |

#### 业界标杆对照（落地参考）

| 标杆来源 | 核心规范 | 我们的对标做法 |
|---------|---------|--------------|
| **微软 Qlib** | 因子参数全部 YAML 声明式配置，表达式引擎动态解析 | L3 配置字典 + `*_config.py`，逐步迁移至 YAML |
| **高盛 gs-quant** | 参数稳定性监控（滚动窗口验证），双阈值预警 | QA-System 增加 `param_stability` 检查器（规划中） |
| **TradingAgents-CN** | 数据源 JSON 化，风控三层参数化，策略参数自动寻优 | `data_config.py` + `config/risk_control.yaml` + 策略 YAML |
| **金融行业代码编写手册** | 常量全大写下划线命名，业务术语准确对应 | `*_config.py` 中全大写命名约定 |

#### 当前项目配置文件清单

| 配置文件 | 层级 | 职责 | 状态 |
|---------|------|------|------|
| `domain/data/data_config.py` | L2 | 数据源/数据库/缓存 | ✅ 已建 |
| `domain/cognition/portrait/portrait_config.py` | L3 | 画像计算参数 | ✅ 已建 |
| `domain/factor/factor_config.py` | L3 | 因子窗口/阈值 | ⚠️ 需补全 |
| `domain/decision/decision_config.py` | L3 | 仓位/风控参数 | ⚠️ 需补全 |
| `config/risk_control.yaml` | L4 | 风控围栏阈值 | 📋 规划中 |
| `config/tail_trade.yaml` | L4 | 尾盘策略参数 | ✅ 已建 |

---

## 四、数据标准（量化特有）

### 4.1 前视偏差（BAN-13）

| 违规模式 | 正确做法 |
|---------|---------|
| 用当天收盘价计算当天因子 | shift(1) 或 lag 昨日数据 |
| 未来函数（peak/vwap 会 lookahead | 严格按时间顺序计算 |
|  survivorship bias | 用历史全样本（包含退市 |

### 4.2 数据质量

| 检查项 | 标准 |
|--------|------|
| 缺失值 | 明确策略（丢弃/填充/跳过） |
| 异常值 | 3σ 或 IQR 检测 |
| 时间戳一致性 | 交易日对齐，时区明确 |
| 复权处理 | 前复权/后复权明确标注 |

---

## 五、测试标准

### 5.1 测试分层

| 层级 | 内容 | 覆盖率要求 |
|------|------|---------|
| 单元测试 | 因子函数、工具函数 | 核心模块 80%+ |
| 集成测试 | 引擎、管线端到端 | 关键路径 100% |
| 回测验证 | 策略回测结果 | 每个策略必跑 |
| 性能测试 | 延迟、吞吐量 | 满足延迟预算内 |

### 5.2 量化特有测试

- [ ] 前视偏差测试：因子计算结果等于  结果应该
- [ ] 数值稳定性测试：相同输入相同输出
- [ ] 边界测试：极端行情、零成交量
- [ ] 精度测试：浮点数精度容忍
- [ ] 回测过拟合检验：样本外验证

---

## 六、QA 门禁标准（10 层门禁）

| 门禁 | 名称 | 检查内容 | 对应标准 |
|------|------|---------|---------|
| Gate0 | 健康检查 | 基础配置、文件格式 | CMMI 2 需求管理 |
| Gate1 | 边界合规 | 分层边界、依赖方向 | ISO 可维护性 |
| Gate2 | 安全基线 | 安全编码、秘密扫描 | OWASP |
| Gate3 | 代码质量 | lint、类型、复杂度 | NASA Power of 10 |
| Gate3.1 | 前视偏差 | 回测未来泄露 | 量化特有 |
| Gate4 | 配置审计 | 配置管理 | CMMI 2 配置管理 |
| Gate5 | 质量保证 | 综合质量评分 | ISO 25010 + CMMI 3 |
| Gate6 | 测试覆盖 | 单元/集成测试 | ISO 可靠性 |
| Gate7 | 性能基线 | 延迟、吞吐量 | CMMI 3 过程监控 |
| Gate8 | 部署准备 | 部署清单、回滚方案 | ISO 可移植性 |
| Gate9 | 合规审计 | ISO/SOX/SLSA | CMMI 4 量化管理 |

---

## 七、模块化与热插拔详细标准

### 7.1 模块接口标准

每个模块必须遵循：

```
module/
├── __init__.py      # 只导出公共 API
├── api.py           # 对外接口（Facade）
├── config.py        # 模块配置
├── engines/        # 核心引擎
├── models/         # 数据模型
└── utils/          # 内部工具
```

**`__init__.py` 只导出，不写实现：

```python
# ✅ 标准
from .api import compute_portrait, PortraitResult

__all__ = ["compute_portrait", "PortraitResult"]
```

### 7.2 插件注册机制

三种注册模式：

**模式 1：装饰器注册（因子/策略）

```python
# registry.py
FACTOR_REGISTRY: Dict[str, Type[BaseFactor]] = {}

def register_factor(name: str):
    def decorator(cls):
        FACTOR_REGISTRY[name] = cls
        return cls
    return decorator

def get_factor(name: str) -> Type[BaseFactor]:
    if name not in FACTORY_REGISTRY:
        raise ValueError(f"未知因子: {name}")
    return FACTOR_REGISTRY[name]
```

**模式 2：配置驱动（数据源/适配器）

```python
# adapter_config.py
ADAPTERS = {
    "tdx": "domain.data.adapters.tdx_adapter.TDXAdapter",
    "ths": "domain.data.adapters.ths_adapter.THSAdapter",
}

def get_adapter(name: str):
    if name not in ADAPTERS:
        raise ValueError(f"未知适配器: {name}")
    module_path, class_name = ADAPTERS[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
```

**模式 3：入口函数列表（检查器/门禁）

```python
# checker_registry.py
CHECKERS = [
    HealthChecker,
    BoundaryChecker,
    CodeBanChecker,
    # ...
]

def run_all_checkers(context):
    results = []
    for checker_cls in CHECKERS:
        checker = checker_cls()
        results.append(checker.run(context))
    return results
```

### 7.3 热插拔 vs 性能权衡

| 模式 | 灵活性 | 运行时性能 | 适用场景 |
|------|--------|-----------|---------|
| 静态导入 | 低 | 最高（0 开销） | 核心模块、性能关键路径 |
| 装饰器注册 | 中 | 高（启动时注册，运行时查表） | 因子、策略 |
| 配置驱动 | 高 | 中（首次加载反射） | 数据源、适配器 |
| 动态 import | 最高 | 低（每次 import 开销） | 插件、扩展模块 |

**量化系统原则：**
- **核心路径（行情→因子→信号→风控→下单）：静态导入，性能第一
- **可扩展部分（因子、策略、数据源）：装饰器/配置驱动，兼顾性能与灵活
- **外围工具（检查器、报告、分析：入口函数列表，易扩展

### 7.4 模块禁用/启用开关

```python
# config.py
MODULE_FLAGS = {
    "adversarial_review": os.environ.get("LINGLONG_ADV_ENABLE", "true").lower() == "true",
    "confidence_fusion": os.environ.get("LINGLONG_CONF_ENABLE", "true").lower() == "true",
}

# 使用时
if MODULE_FLAGS["adversarial_review"]:
    from .adversarial_review import run_review
```

---

## 八、性能优化标准（量化速度优先）

### 8.1 量化性能优化 checklist

- [ ] 核心循环用 numpy/pandas 向量化
- [ ] 避免 iterrows / itertuples
- [ ] 数据库批量查询，避免 N+1
- [ ] 常用因子预计算缓存
- [ ] 热数据内存缓存（LRU）
- [ ] 冷数据延迟加载
- [ ] 字符串操作最小化
- [ ] 对象创建最小化
- [ ] 内存复用
- [ ] Profiling 定位瓶颈

### 8.2 性能测试标准

```python
# 性能装饰器
import time
from functools import wraps

def latency_budget(limit_ms: int):
    """延迟预算装饰器 — 超过阈值告警"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > limit_ms:
                logger.warning(f"{func.__name__} 耗时 {elapsed:.1f}ms > {limit_ms}ms")
            return result
        return wrapper
    return decorator
```

---

## 九、代码审查标准

### 9.1 PR 审查 checklist

**业务逻辑：
- [ ] 需求映射正确
- [ ] 边界情况处理
- [ ] 数值正确性（精度）
- [ ] 时间处理（时区）
- [ ] 前视偏差检查

**架构合规：
- [ ] 分层边界
- [ ] 配置分离
- [ ] 依赖声明
- [ ] 模块化

**性能：
- [ ] 向量化
- [ ] N+1 查询
- [ ] 缓存策略

**安全：
- [ ] 异常处理
- [ ] 输入校验
- [ ] 秘密扫描

---

## 十、标准符合性矩阵

| 标准 | 对应检查 | 门禁 |
|------|---------|------|
| ISO 25010 功能合适性 | Gate3 | Gate3 |
| ISO 25010 性能效率 | performance_check + 性能基线 | Gate7 |
| ISO 25010 可靠性 | 测试 + 异常处理 | Gate5/Gate6 |
| ISO 25010 安全性 | security + code_ban | Gate2/Gate5 |
| ISO 25010 可维护性 | codestyle + deadcode | Gate3/Gate5 |
| NASA Power of 10 | code_ban | Gate3 |
| OWASP Top 10 | securityplus + secret | Gate2 |
| CMMI 2/3/4 | 全门禁 | Gate0/4/5/7/9 |
| SLSA Level 2 | CI + 依赖 | Gate8 |
| SOX | WORM + 审计 | Gate9 |

---

## 十一、量化专项审查标准（补全）

> 以下审查项对标业界标杆（Qlib/gs-quant/TradingAgents-CN），按量化 A++ 标准补全。

### 11.1 参数配置完整性审查（CONFIG-01 ~ CONFIG-03）

> 对标：微软 Qlib 声明式配置 + TradingAgents-CN 配置分离

| 审查项 | 检查内容 | 严重程度 | 对应检查器 |
|--------|---------|---------|-----------|
| **CONFIG-01** | L2 基础设施参数是否全部在 `data_config.py` 中 | 🟡 警告 | config_audit |
| **CONFIG-02** | L3 领域参数是否全部在 `*_config.py` 中（因子窗口、阈值、权重） | 🟡 警告 | config_audit |
| **CONFIG-03** | L4 策略参数是否在 `config/*.yaml` 中（止损、止盈、仓位上限） | 🟡 警告 | config_audit |

**判定标准**：
- 扫描 `domain/` 和 `shared/` 下所有 `.py` 文件
- 检测硬编码的因子窗口（如 `period=20`）、阈值（如 `stop_loss=-0.05`）
- 若已在 `*_config.py` 中定义则豁免，否则报告 CONFIG-02

### 11.2 参数稳定性审查（STAB-01 ~ STAB-03）

> 对标：高盛 gs-quant 滚动窗口验证 + 双阈值预警

| 审查项 | 检查内容 | 严重程度 | 实现方式 |
|--------|---------|---------|---------|
| **STAB-01** | 核心策略参数是否有滚动窗口验证记录 | 🟢 建议 | QA 报告中标注 |
| **STAB-02** | 参数变化是否超过 2σ 预警阈值 | 🟡 警告 | 运行时监控 |
| **STAB-03** | R² 下降是否超过 20% 重优化阈值 | 🟡 警告 | 运行时监控 |

**滚动窗口验证规范**：
- 窗口大小：策略调仓周期的 3-5 倍（默认 60 个交易日）
- 滑动步长：调仓周期（默认 20 个交易日）
- 预警双阈值：R² 下降 20% 或系数变化超 2σ

### 11.3 风控配置审查（RISK-01 ~ RISK-03）

> 对标：TradingAgents-CN `risk_management.yaml` 三层参数化

| 审查项 | 检查内容 | 严重程度 | 对应检查器 |
|--------|---------|---------|-----------|
| **RISK-01** | 风控阈值是否在 `config/risk_control.yaml` 中配置 | 🟡 警告 | config_audit |
| **RISK-02** | 风控参数是否在 FENCE 围栏 [min, max] 范围内 | 🔴 阻断 | fusedetect |
| **RISK-03** | 风控参数变更是否记录审计日志 | 🟢 建议 | production |

### 11.4 补全审查项与现有检查器映射

| 新增审查项 | 现有检查器覆盖 | 差距 | 落地优先级 |
|-----------|--------------|------|-----------|
| CONFIG-01~03 | config_audit（已有框架） | 扫描逻辑需补全 | P1 |
| STAB-01~03 | 无（规划中） | 新建 `param_stability` 检查器 | P2 |
| RISK-01 | config_audit（已有框架） | YAML 扫描规则需补全 | P1 |
| RISK-02 | fusedetect（已有框架） | FENCE 校验逻辑已有 | ✅ |
| RISK-03 | production（已有框架） | 审计日志检查需补全 | P2 |

---

*本文档随系统演进，v1.0
