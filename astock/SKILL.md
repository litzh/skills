---
name: astock
description: 个人 A 股交易数据分析工具。导入券商导出的资金流水和成交记录，抓取历史日K线，分析持仓、盈亏、交易磨损，绘制带交易标注的K线图。
---

# astock — A 股交易数据分析

数据库位于 `~/.local/share/astock/astock.db`。

环境变量（配置于 `~/.config/skills.env`）：
- `TUSHARE_TOKEN` — tushare API token（抓取 K线必须）

---

## 导入交易数据

从券商导出 TSV 格式的资金流水和成交记录后导入：

```bash
astock import --money money.tsv      # 导入资金流水
astock import --stock stock.tsv      # 导入成交记录
astock import --money money.tsv --stock stock.tsv  # 同时导入
```

---

## 抓取 K 线数据

```bash
astock fetch                         # 自动从成交记录提取标的，增量抓取到昨天
astock fetch --codes 600519 518880   # 指定标的
astock fetch --start 2024-01-01 --end 2024-12-31
```

数据来源为 tushare，若不可用可手动下载 CSV 导入：

```bash
# CSV 须含列：date/trade_date、open、high、low、close（列名宽松匹配中英文）
astock import --kline 518880.csv --code 518880
astock import --kline 600519.csv --code 600519
```

---

## 持仓与盈亏分析

```bash
astock summary    # 账户总览（净入金、总资产、总盈亏）
astock position   # 当前持仓明细（成本、市值、浮动盈亏、仓位占比）
astock pnl        # 盈亏分析（已实现 + 浮动，分已清仓/持仓）
astock friction   # 交易磨损分析（费用明细、做T损耗）
```

---

## K 线图

```bash
astock chart 600519                          # 绘制全部历史K线
astock chart 518880 --start 2024-01-01       # 指定起始日期
astock chart 600519 --output mao.png         # 指定输出路径
astock chart 600519 --show                   # 绘制并弹窗显示
```

图表自动在买卖点标注：`B`（买入）、`S`（卖出）、`T`（做T）。

---

## 数据目录

| 路径 | 内容 |
|------|------|
| `~/.local/share/astock/astock.db` | SQLite 数据库（交易记录、K线） |

数据库不存在时首次运行自动创建。
