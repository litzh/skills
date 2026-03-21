---
name: nmc-weather
description: 中央气象台（NMC）天气查询工具。支持查询全国省市列表和城市天气预报（实况、空气质量、7天预报、预警），输出文本或 JSON 格式。必须在 nmc-weather/ 目录下运行。
---

# NMC 天气查询工具 — AI 调用指南

本工具基于中央气象台（NMC）API，提供省市列表查询和城市天气预报查询。

## 执行方式

所有命令通过 `uv run` 在项目目录下执行：

```
uv run python weather.py <command> [options]
```

## 命令参考

### 查询所有地区

```
uv run python weather.py list
```

返回全国所有省级行政区的名称和代码。

### 查询地区下的城市列表

按名称查询（精确匹配）：
```
uv run python weather.py list --name <地区名>
```

按代码查询：
```
uv run python weather.py list --code <地区代码>
```

返回该地区下所有城市及其站点代码（station code）。

### 查询城市天气

按站点代码查询（推荐，唯一确定）：
```
uv run python weather.py weather --code <站点代码>
```

按城市名查询：
```
uv run python weather.py weather --name <城市名>
```

### 输出格式

所有命令均支持 `--format` 参数，放在子命令之前：

```
uv run python weather.py --format json weather --code <站点代码>
uv run python weather.py --format json list --name <地区名>
```

- `text`（默认）：人类可读的纯文本表格
- `json`：精简结构化 JSON，适合程序解析

## 典型工作流

**目标：查询某城市天气**

1. 如果已知站点代码，直接查询：
   ```
   uv run python weather.py weather --code <站点代码>
   ```

2. 如果只知道城市名，先尝试按名称查询：
   ```
   uv run python weather.py weather --name <城市名>
   ```
   - 若城市名唯一，直接返回天气。
   - 若存在同名城市，命令会报错并列出所有候选项（含省份和站点代码），此时应改用 `--code` 精确查询。

3. 如果不知道城市名对应的代码，可通过两步查找：
   ```
   uv run python weather.py list                    # 找到目标地区的代码
   uv run python weather.py list --code <地区代码>   # 找到目标城市的站点代码
   uv run python weather.py weather --code <站点代码>
   ```

## 输出字段说明

### weather 文本输出

```
# 北京 (北京市)  [站点: Wqsps]
更新时间: 2026-03-13 12:25

## 当前实况
天气: 多云  气温: 7.2°C (体感 4.5°C)
湿度: 47.0%  风向: 东北风 微风 (2.2 m/s)
日出: 06:29  日落: 18:18

## 空气质量
AQI: 89  等级: 良

## 未来7天预报
日期          白天                  夜间                  降水(mm)
------------------------------------------------------------
2026-03-13  小雨 8°C 南风微风  ...
```

### weather JSON 输出结构

```json
{
  "station": {
    "code": "Wqsps",
    "name": "北京",
    "region": "北京市"
  },
  "publish_time": "2026-03-13 12:25",
  "current": {
    "weather": "多云",
    "temperature": 7.2,
    "feels_like": 4.5,
    "humidity_pct": 47.0,
    "wind_direction": "东北风",
    "wind_power": "微风",
    "wind_speed_ms": 2.2,
    "sunrise": "2026-03-13 06:29",
    "sunset": "2026-03-13 18:18"
  },
  "air_quality": {
    "aqi": 89,
    "level": "良"
  },
  "alert": null,
  "forecast": [
    {
      "date": "2026-03-13",
      "day": {
        "weather": "小雨",
        "temp": 8,
        "wind_direction": "南风",
        "wind_power": "微风"
      },
      "night": {
        "weather": "小雨",
        "temp": 4,
        "wind_direction": "东北风",
        "wind_power": "微风"
      },
      "precipitation_mm": 2.1
    }
  ]
}
```

**字段说明：**
- `alert`：气象预警内容，无预警时为 `null`
- `forecast`：未来 7 天逐日预报
- `precipitation_mm`：当日降水量（毫米）
- API 无效值（原始值 `9999`）统一处理为 `null`

## 注意事项

- `--name` 参数为**精确匹配**，例如地区名需填写完整名称（`北京市` 而非 `北京`）。
- 优先使用 `--code` 查询，避免同名歧义，也可减少一次 API 请求。
- 命令执行失败时错误信息输出到 stderr，退出码为 1。
