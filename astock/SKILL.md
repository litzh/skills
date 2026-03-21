---
name: astock
description: A股ETF投资组合回测与再平衡工具。支持阈值+定期再平衡策略回测，与买入持有基准对比；并可基于实际持仓给出即时再平衡建议。必须在 astock/ 目录下运行。
---

# A股投资组合回测工具使用指南

本工具对 ETF 投资组合进行历史回测，支持阈值+定期再平衡策略，并与买入持有基准自动对比。

## 运行命令

所有命令均在项目根目录 `astock` 下执行，使用 `uv run` 运行。

```bash
# 基本用法（时间范围读取配置文件）
uv run python backtest.py config/portfolio.toml

# 覆盖时间范围（优先级高于配置文件）
uv run python backtest.py config/portfolio.toml --start 2020-01-01 --end 2023-12-31

# 只覆盖开始日期，结束日期默认今日
uv run python backtest.py config/portfolio.toml --start 2022-01-01

# 指定 HTTP 代理（IP 被封时使用）
uv run python backtest.py config/portfolio.toml --proxy 127.0.0.1:7890
```

## 缓存机制

- 配置文件内容 + 生效的时间范围共同决定缓存 key（SHA256）
- 相同配置和时间范围再次运行时**直接读取缓存**，无需重新拉取数据和计算
- 修改配置文件任意字段，或通过命令行改变时间范围，均会触发重新回测并更新缓存
- 缓存文件存放于 `cache/` 目录，格式为 `{hash前12位}.pkl`

## 输出内容

1. **策略对比汇总**：主策略 vs 买入持有，包含总收益率、年化收益率、年化波动率、夏普比率、最大回撤
2. **再平衡记录**：每次触发的日期、原因、各资产再平衡前权重、买卖金额明细
3. **各资产期末表现**：两种策略下各资产的期末市值、占比、单资产收益率
4. **CSV 导出**：主策略每日快照导出至配置文件同目录，文件名为 `backtest_{组合名}.csv`

---

## 配置文件格式说明

配置文件为 TOML 格式，存放于 `config/` 目录。以下是完整字段说明。

### [meta] 基本信息

```toml
[meta]
name  = "投资组合"       # 组合名称，用于报告标题和 CSV 文件名
start = "2025-01-02"    # 回测开始日期，格式 YYYY-MM-DD
end   = "2025-12-31"    # 回测结束日期，留空则默认使用今日
```

- `start` / `end` 可被命令行 `--start` / `--end` 覆盖

### [portfolio] 资金设置

```toml
[portfolio]
total_capital = 1_000_000   # 总初始资金（元），按各资产 weight 比例分配
```

- 数字支持下划线分隔，`1_000_000` 等同于 `1000000`
- 各资产实际初始资金 = `total_capital × weight`

### [assets.{ETF代码}] 资产定义

每个资产单独一个段，段名中的代码即为 ETF/股票代码。

```toml
[assets.518880]
name    = "黄金ETF"  # 资产名称，用于报告展示
weight  = 0.25      # 目标权重，所有资产 weight 之和必须等于 1.0
is_cash = false     # false：通过东方财富接口获取前复权日K线
```

**现金类资产**（货币基金等）使用固定利率模拟，不请求行情接口：

```toml
[assets.511620]
name      = "货币ETF"
weight    = 0.25
is_cash   = true     # true：以固定年化利率模拟收益
cash_rate = 0.015    # 年化利率，0.015 表示 1.5%
```

**权重规则：**
- 所有资产的 `weight` 之和必须严格等于 `1.0`，否则程序报错退出
- 支持非均等权重，例如 `0.60 / 0.20 / 0.20`

**行情数据说明：**
- `is_cash = false` 的资产从东方财富接口获取**前复权**日K线，分红自动计入价格
- 沪市 ETF（代码以 `5` 或 `6` 开头）和深市 ETF（其他开头）均支持

### [strategy] 再平衡策略

```toml
[strategy]
type = "threshold_and_periodic"   # 策略类型，见下方说明
```

**strategy.type 可选值：**

| 值 | 说明 |
|----|------|
| `threshold_and_periodic` | 阈值触发 + 定期触发（两者取并集，同一天只执行一次） |
| `threshold_only` | 仅阈值触发 |
| `periodic_only` | 仅定期触发 |
| `buy_and_hold` | 不再平衡（此时主策略等同于买入持有基准） |

> 无论主策略是什么，报告始终额外运行一次买入持有作为对比基准。

### [strategy.params] 策略参数

```toml
[strategy.params]
drift           = 0.05         # 相对偏差阈值（适用于含阈值触发的策略）
periodic_months = [3, 6, 9, 12]  # 定期再平衡月份（适用于含定期触发的策略）
```

**drift（相对偏差阈值）：**
- 任意资产实际权重偏离其**目标权重**超过 `±drift` 即触发再平衡
- 基于目标权重的相对偏差，自动适配非均等组合：
  - 目标 20%，drift=0.05 → 触发区间 [15%, 25%]
  - 目标 60%，drift=0.05 → 触发区间 [55%, 65%]
- 默认值：`0.05`

**periodic_months（定期再平衡月份）：**
- 整数数组，取对应月份的**最后一个交易日**触发再平衡
- `[3, 6, 9, 12]` 表示每季度末再平衡
- `[6, 12]` 表示每年 6 月底和 12 月底各再平衡一次
- 默认值：`[3, 6, 9, 12]`

---

## 完整配置示例

### 均等四资产组合

```toml
[meta]
name  = "投资组合"
start = "2025-01-02"
end   = "2025-12-31"

[portfolio]
total_capital = 1_000_000

[assets.510300]
name    = "沪深300ETF"
weight  = 0.25
is_cash = false

[assets.518880]
name    = "黄金ETF"
weight  = 0.25
is_cash = false

[assets.511620]
name      = "货币ETF"
weight    = 0.25
is_cash   = true
cash_rate = 0.015

[assets.511090]
name    = "30年国债ETF"
weight  = 0.25
is_cash = false

[strategy]
type = "threshold_and_periodic"

[strategy.params]
drift           = 0.05
periodic_months = [3, 6, 9, 12]
```

### 非均等权重组合（仅阈值触发）

```toml
[meta]
name  = "激进成长组合"
start = "2020-01-01"
end   = ""

[portfolio]
total_capital = 500_000

[assets.510300]
name    = "沪深300ETF"
weight  = 0.60
is_cash = false

[assets.518880]
name    = "黄金ETF"
weight  = 0.20
is_cash = false

[assets.511620]
name      = "货币ETF"
weight    = 0.20
is_cash   = true
cash_rate = 0.015

[strategy]
type = "threshold_only"

[strategy.params]
drift = 0.10
```

---

## 注意事项

- 回测起始日必须是交易日，建议使用每年第一个交易日（通常为 1 月 2 日前后）
- ETF 代码须为 6 位数字，且在东方财富有行情数据
- 修改配置文件注释不影响 hash，但修改任何字段值均会使缓存失效
- `cache/` 和 `config/backtest_*.csv` 已加入 `.gitignore`，不会提交到版本库

---

# 持仓实时再平衡工具使用指南

基于当前实际持仓和策略配置，查询最新价格，判断是否需要立即再平衡并给出买卖建议。

## 运行命令

```bash
# 基本用法（持仓与策略不匹配时报错退出）
uv run python rebalance_now.py config/holdings.toml config/portfolio.toml

# 强制模式：卖出持仓中多余资产，买入策略中缺少资产
uv run python rebalance_now.py config/holdings.toml config/portfolio.toml --force

# 指定最小交易金额（低于此金额的操作忽略，默认 1000 元）
uv run python rebalance_now.py config/holdings.toml config/portfolio.toml --min-trade 500

# 指定 HTTP 代理（IP 被封时使用）
uv run python rebalance_now.py config/holdings.toml config/portfolio.toml --proxy 127.0.0.1:7890
```

## 持仓配置文件格式（config/holdings.toml）

```toml
[meta]
name = "我的持仓"   # 组合名称，用于报告标题

[holdings.510300]
name   = "沪深300ETF"
shares = 180000         # 持有份额，程序自动查询最新价格计算市值

[holdings.518880]
name   = "黄金ETF"
shares = 25000

[holdings.511620]
name   = "货币ETF"
shares = 2500           # 货基通常 1份≈1元，填份额即可
# value = 2500.00       # 若接口查询失败，取消注释并手动填写当前市值（元）

[holdings.511090]
name   = "30年国债ETF"
shares = 2500
```

**说明：**
- 所有资产（含现金类）统一填 `shares`，程序自动查询最新净值/价格计算市值
- 若某资产接口查询失败，在配置中补充 `value` 字段（当前市值，元）作为兜底
- 持仓中的资产代码必须与策略配置文件中的 `[assets]` 完全一致，否则报错

## 一致性校验规则

| 情况 | 默认行为 | --force 行为 |
|------|----------|--------------|
| 持仓有，策略无（多余资产） | 报错退出 | 建议全部卖出 |
| 策略有，持仓无（缺少资产） | 报错退出 | 建议按目标权重买入 |
| 完全一致 | 正常分析 | 正常分析 |

## 输出内容

1. **当前持仓状况**：各资产现价、份额、市值、当前占比 vs 目标占比、偏差（超阈值标记 `!`）
2. **再平衡判断**：是否触发（超阈值 / 存在多余或缺少资产）及原因
3. **操作建议**：各资产买卖金额、份额变动、参考价（买入向下取整，卖出向下取整）
4. **注意事项**：取整误差、货基赎回延迟提示等
