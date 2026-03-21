---
name: remote
description: Broadlink 红外智能遥控器 CLI 工具。管理设备和红外按键方案，发送红外指令。必须在 remote/ 目录下运行。
---

# remote CLI 使用指南

本工具通过命令行控制 Broadlink 红外智能遥控器。

**必须在 `remote/` 目录下运行** — 配置文件路径相对于当前目录读写。

所有命令格式：`uv run remote.py <子命令>`。

---

## 初次配置

克隆仓库后，`config/devices.toml` 不包含在版本库中（含设备 MAC 地址和内网 IP）。从示例文件创建：

```bash
cp config/devices.toml.example config/devices.toml
```

然后手动填写设备信息，或使用交互式扫描自动添加：

```bash
# 自动发现局域网内的 Broadlink 设备并交互保存
uv run remote.py device scan
uv run remote.py device add living
```

`config/config.toml` 和 `config/plans/` 已提交到版本库，克隆后可直接使用。

---

## 设备管理

```bash
# 扫描局域网内的 Broadlink 设备
uv run remote.py device scan

# 列出已保存的设备（* 标记默认设备）
uv run remote.py device list

# 交互式添加设备（扫描局域网，提示输入名称和 IP 模式）
uv run remote.py device add <名称>

# 删除已保存的设备
uv run remote.py device remove <名称>

# 设置默认设备（省略 --device 时使用）
uv run remote.py device default <名称>
```

---

## 方案管理

**方案（plan）** 是一组命名的红外按键集合（如 "gree-ac"、"sony-bravia-tv"）。方案与设备解耦，同一方案可通过任意设备发送。

```bash
# 列出所有已保存的方案
uv run remote.py plan list

# 查看方案中的所有按键
uv run remote.py plan show <方案>

# 学习单个红外按键并保存到方案
uv run remote.py plan learn <方案> <按键>

# 交互式批量学习（输入 'stop' 结束）
uv run remote.py plan learn --interactive <方案>
# 简写：
uv run remote.py plan learn -i <方案>
```

**学习流程：**
1. 运行 learn 命令。
2. 将原始遥控器对准 Broadlink 设备。
3. 按下要学习的按键。
4. 按 Enter 确认捕获 — 红外码以给定的按键名存储。

---

## 发送指令

```bash
# 使用默认设备发送指令
uv run remote.py control <方案> <按键>

# 使用指定设备发送指令
uv run remote.py control --device <名称> <方案> <按键>
```

---

## 配置文件

| 路径 | 用途 |
|------|------|
| `config/config.toml` | 全局设置：默认设备、超时时间 |
| `config/devices.toml` | 已保存的设备（MAC、IP 模式、缓存） |
| `config/plans/<名称>.toml` | 各方案的红外按键码 |

---

## 完整示例

```bash
# 1. 扫描并保存设备
uv run remote.py device scan
uv run remote.py device add living    # 交互式：选择设备，选择 dhcp/static

# 2. 学习客厅空调的红外按键
uv run remote.py plan learn -i gree-ac
#    -> 输入按键名，如：power-on、power-off、temp-up、temp-down、mode-cool

# 3. 发送指令
uv run remote.py control gree-ac power-on
uv run remote.py control gree-ac temp-up
uv run remote.py control sony-bravia-tv volume-up
```
