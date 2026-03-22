---
name: health
description: 解析 iPhone Health 快捷指令导出的 JSON 文件，按指标分类输出健康数据摘要，支持睡眠结构、HRV、心率、活动能量等。
---

# Health 数据解析

解析 iPhone 健康数据 JSON 文件（由快捷指令导出至 iCloud），输出纯文本报告供 AI 分析。

## 使用方式

```bash
# 解析单个文件（默认 cn 单位制）
uv run python health.py path/to/metric.json

# 解析目录下所有 JSON 文件
uv run python health.py -d path/to/dir

# 指定单位制
uv run python health.py -d path/to/dir --unit si   # 国际单位（kJ、min）
uv run python health.py -d path/to/dir --unit cn   # 习惯单位（千卡、分钟），默认
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `file` | 单个 JSON 文件路径 |
| `-d / --dir` | 目录路径，解析其中所有 `.json` 文件 |
| `--unit si\|cn` | 单位制：`cn` 习惯单位（默认），`si` 国际单位 |

## 支持的指标

| 指标名 | 说明 |
|--------|------|
| `sleep_analysis` | 睡眠分析：入睡/起床时间、各阶段时长占比、结构序列 |
| `heart_rate_variability` | HRV：均值、范围、各时间点数值 |
| `resting_heart_rate` | 静息心率 |
| `active_energy` | 活动能量（cn: 千卡，si: kJ） |
| `time_in_daylight` | 日光暴露时间（cn: 分钟，si: min） |

## 输出示例

```
[睡眠分析]
  入睡: 01:44  起床: 08:55  总时长: 7h11m
  核心: 3h58m (55%)
  深度: 1h04m (15%)
  快速动眼期: 2h08m (30%)
  结构序列: 核心(27m) → 深度(17m) → 核心(15m) → ...

[活动能量]
  2026-03-22: 78 千卡

[心率变异性 (HRV)]
  均值: 48.8 ms  范围: 22.9–82.3 ms  测量次数: 7
  01:40  82.3 ms
  ...
```
