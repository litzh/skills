---
name: zigbee
description: 通过 Zigbee2MQTT 使用 MQTT 协议控制 Zigbee 设备。
metadata: {"clawdbot":{"emoji":"💡","os":["linux","darwin"],"requires":{"bins":["uv"]}}}
---

# Zigbee 设备控制

本工具通过 `zigbee` 命令经由 Zigbee2MQTT 控制 Zigbee 设备。

## 前置配置

在 `~/.config/skills.env` 中配置环境变量（自动加载）：

```bash
ZIGBEE_BROKER=<mqtt_broker_ip>   # 必须
ZIGBEE_DEVICE=<friendly_name>    # 大多数命令必须
ZIGBEE_PORT=1883                 # 可选，默认 1883
```

或直接在命令中传入：

```bash
zigbee --broker <ip> --device <name> <命令>
```

## 使用流程

### 第一步：查看设备能力

```bash
zigbee info
```

若设备已在缓存中，将输出其型号、厂商和完整能力列表，可直接跳至第三步。

### 第二步：设备不在缓存中 — 执行扫描

若 `info` 提示 "No device cache found" 或 "device not in cache"：

```bash
zigbee scan
```

该命令从 `zigbee2mqtt/bridge/devices` 获取所有设备，保存至 `~/.local/share/zigbee/devices.json`，并打印发现的设备列表。之后重试 `info`。

列出缓存中的设备（不重新扫描）：

```bash
zigbee scan --list
```

### 第三步：根据能力发送命令

只发送设备实际支持的命令（通过 `info` 确认）。

**state** — 开 / 关 / 切换：
```bash
zigbee on
zigbee off
zigbee toggle
```

**brightness** — 值 0-254 或百分比：
```bash
zigbee brightness 128
zigbee brightness 50%
```

**color_temp** — mired 值、百分比或预设名称：
```bash
zigbee temp 300
zigbee temp 50%
zigbee temp warm      # 预设：coolest、cool、neutral、warm、warmest
```

**color** — 推荐使用十六进制或 R,G,B；也支持 x/y（CIE 1931）：
```bash
zigbee color "#FF5500"
zigbee color 255,85,0
zigbee color x:0.3,y:0.4
```

注：设备原生色彩空间为 CIE 1931 xy，Zigbee2MQTT 会在内部将十六进制/RGB 转换为 xy，因此推荐使用十六进制或 RGB 格式。通过 `get` 读取状态时，颜色以 xy 格式返回。

**effect** — 触发灯光特效：
```bash
zigbee effect colorloop
zigbee effect stop_colorloop
# 可用值见 `info` 输出
```

**do_not_disturb** — 断电后保持关闭状态：
```bash
zigbee dnd on
zigbee dnd off
```

**color_power_on_behavior** — 上电恢复行为：
```bash
zigbee poweron previous    # initial / previous / customized
```

**set** — 一条命令设置多个属性：
```bash
zigbee set --state on --brightness 80% --temp warm --transition 2
zigbee set --state on --on-time 300    # 300 秒后自动关闭
```

**get** — 读取当前设备状态：
```bash
zigbee get                        # 所有字段
zigbee get state brightness       # 指定字段
```

## 注意事项

- 发送命令前务必先执行 `info`，不要假设设备能力。
- 设备不支持 `effect` 或 `color` 时，对应命令会报错。
- 百分比基于缓存中设备的实际最小/最大值换算。
- `brightness`、`temp`、`color`、`set` 命令均支持 `--transition`（秒），用于平滑过渡。
- 设备缓存：`~/.local/share/zigbee/devices.json`。Zigbee2MQTT 中新增或重命名设备后，需重新执行 `scan`。
