# Skills

个人 CLI 工具集，供 AI Agent 直接调用。每个 skill 是一个独立子目录，通过 `install.py` 安装到 `~/.local/bin/`。

## 安装

依赖 [uv](https://docs.astral.sh/uv/)。

```bash
# 安装全部
uv run python install.py

# 只安装指定 skill
uv run python install.py zigbee
```

安装内容：
- 各 skill 的依赖同步到各自目录的 `.venv/`
- wrapper 脚本写入 `~/.local/bin/<cmd>`
- 首次安装时初始化配置文件（不覆盖已有文件）

确保 `~/.local/bin` 在 `PATH` 中：
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

## 凭证配置

各工具运行时自动加载 `~/.config/skills.env`，在此文件中配置所需凭证：

```sh
# zigbee
ZIGBEE_BROKER=192.168.1.x
ZIGBEE_DEVICE=my-light

# astock
TUSHARE_TOKEN=xxx

# ys7（萤石摄像头）
YS7_APP_KEY=xxx
YS7_APP_SECRET=xxx
YS7_DEVICE_SERIAL=xxx
YS7_DEVICE_IP=192.168.1.x
YS7_DEVICE_PASSWORD=xxx
```

文件仅在调用命令时加载，不会污染 shell 环境。

---

## 工具列表

### `zigbee` — Zigbee 设备控制

通过 Zigbee2MQTT 控制 Zigbee 设备（灯光、开关等）。

**必须配置：** `ZIGBEE_BROKER`、`ZIGBEE_DEVICE`

```bash
zigbee --broker 192.168.1.x --device my-light on
zigbee scan                  # 扫描并缓存所有设备
zigbee info                  # 查看设备能力
zigbee on / off / toggle
zigbee brightness 80%
zigbee temp warm
zigbee color "#FF5500"
zigbee set --state on --brightness 80% --temp warm
zigbee get
```

数据目录：`~/.local/share/zigbee/`

---

### `remote` — 红外遥控器

通过 Broadlink 设备发送红外指令。

```bash
remote device scan           # 扫描局域网内的 Broadlink 设备
remote device list
remote device add living
remote plan list             # 列出所有方案
remote plan show gree-ac
remote plan learn -i gree-ac # 交互式学习按键
remote control gree-ac on
remote control gree-ac temp-up
```

配置目录：`~/.config/remote/`（含 `config.toml`、`devices.toml`、`plans/`）

---

### `tieba` — 百度贴吧数据抓取

增量抓取贴吧帖子与用户数据，支持按 IP、关键词过滤。

```bash
tieba fetch 天堂鸡汤 -n 50   # 抓取最近50个帖子
tieba query --brief           # 查询所有缓存贴吧的活跃用户
tieba query --fname 天堂鸡汤 --ip 广东
tieba query --keyword 推荐 --json
tieba clear                   # 清除缓存
```

缓存目录：`~/.cache/tieba/`

---

### `astock` — A 股交易数据分析

**必须配置：** `TUSHARE_TOKEN`

导入券商导出的资金流水和成交记录，抓取历史日K线，分析持仓、盈亏、交易磨损，绘制带交易标注的K线图。

```bash
# 导入交易数据（券商导出 TSV）
astock import --money money.tsv --stock stock.tsv

# 抓取 K 线（增量，自动提取持仓标的）
astock fetch
astock fetch --codes 600519 518880

# 手动导入 K 线 CSV（tushare 导出格式，或含 date/open/high/low/close 的 CSV）
astock import --kline 518880.csv          # 自动从 ts_code 列提取代码
astock import --kline data.csv --code 600519

# 分析
astock summary    # 账户总览（净入金、总资产、总盈亏）
astock position   # 当前持仓明细
astock pnl        # 盈亏分析（已实现 + 浮动）
astock friction   # 交易磨损分析（费用 + 做T损耗）

# K 线图
astock chart 600519
astock chart 518880 --start 2024-01-01 --output gold.png
```

数据目录：`~/.local/share/astock/`

---

### `ys7` — 萤石摄像头

纯 curl 调用，无独立命令。参考 `ys7/SKILL.md`。

**内网 RTSP 直连：**
```
rtsp://admin:<YS7_DEVICE_PASSWORD>@<YS7_DEVICE_IP>:554/h264/ch1/main/av_stream
```

**外网 HLS 流：**
```bash
# 1. 获取 accessToken
curl -X POST "https://open.ys7.com/api/lapp/token/get?appKey=${YS7_APP_KEY}&appSecret=${YS7_APP_SECRET}"

# 2. 获取播放地址
curl -X POST https://open.ys7.com/api/lapp/v2/live/address/get \
    --form "accessToken=${YS7_ACCESS_TOKEN}" \
    --form "deviceSerial=${YS7_DEVICE_SERIAL}" \
    --form "protocol=2"
```

---

## 数据目录

| 工具 | 路径 | 用途 | 覆盖变量 |
|------|------|------|---------|
| zigbee | `~/.local/share/zigbee/` | 设备缓存 | `ZIGBEE_DATA_DIR` |
| remote | `~/.config/remote/` | 配置、设备、方案 | `REMOTE_CONFIG_DIR` |
| tieba | `~/.cache/tieba/` | 抓取缓存 | `TIEBA_CACHE_DIR` |
| astock | `~/.local/share/astock/` | SQLite 数据库 | `ASTOCK_DATA_DIR` |
