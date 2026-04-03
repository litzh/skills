# remote

基于 python-broadlink 的命令行红外遥控器管理工具，支持设备管理、信号学习和远程控制。

---

## 功能概览

- **device** — 遥控器设备的发现与管理，持久化设备信息
- **plan** — 遥控方案管理，学习并保存红外信号（方案与设备解耦）
- **control** — 向指定设备发送指定方案中的指定按键信号

---

## 目录结构

```
config/
  config.toml         # 全局配置（默认设备、超时参数等）
  devices.toml        # 已保存的设备列表
  plans/
    ac.toml           # 空调遥控方案
    tv.toml           # 电视遥控方案
    ...
  .tmp/
    ac.toml.tmp       # 交互式学习过程中的临时文件
```

---

## 配置文件格式

### config/config.toml

```toml
default_device = "living-rm"   # 默认设备名，control 命令省略 --device 时使用

[settings]
learn_timeout = 10             # 学习模式等待信号的超时时间（秒）
dhcp_cache_ttl = 86400         # DHCP 设备 IP 缓存有效期（秒，默认 1 天）
```

### config/devices.toml

```toml
[[devices]]
name = "living-rm"
mac = "AA:BB:CC:DD:EE:FF"
model = "RM4 mini"
ip_mode = "dhcp"               # "dhcp" 或 "static"
cached_ip = "192.168.1.100"   # DHCP 模式下缓存的 IP
cache_time = "2024-01-01T12:00:00"  # 缓存时间，用于判断是否过期

[[devices]]
name = "bedroom"
mac = "AA:BB:CC:DD:EE:FE"
model = "RM4 mini"
ip_mode = "static"
ip = "192.168.1.101"
```

### config/plans/ac.toml

```toml
name = "ac"
description = "空调遥控"

[[keys]]
name = "power-on"
code = "26004e00..."           # IR 信号，hex 编码

[[keys]]
name = "power-off"
code = "26004e00..."
```

---

## 命令说明

### device 子命令

```bash
# 扫描局域网，发现 Broadlink 设备
remote device scan

# 列出已保存的所有设备
remote device list

# 手动添加设备（交互式，选择 IP 模式、输入别名等）
remote device add <name>

# 删除已保存的设备
remote device remove <name>

# 设置默认设备（写入 config/config.toml）
remote device default <name>
```

### plan 子命令

```bash
# 列出所有已保存的遥控方案
remote plan list

# 查看指定方案下的所有按键
remote plan show <plan>

# 学习单个按键（方案不存在时提示是否创建）
remote plan learn <plan> <key>

# 交互式学习：循环学习多个按键，随时可输入 stop 结束
remote plan learn --interactive <plan>
```

**学习流程：**
1. 进入学习模式后，将遥控器对准 Broadlink 设备
2. 按下目标按键
3. 按回车确认，程序读取信号（最多等待 `learn_timeout` 秒）
4. 输入按键名称保存（如 `power-on`、`cool-16`）
5. 如果按键名已存在，提示是否覆盖
6. 交互式模式下，输入 `stop` 结束并提交保存

**交互式学习临时文件机制：**
- 学习过程中写入 `config/.tmp/<plan>.toml.tmp`
- 输入 `stop` 后询问是否保存，确认后整体替换 `config/plans/<plan>.toml`
- 中途强制退出则临时文件保留，下次启动时提示是否恢复

### control 子命令

```bash
# 发送指令（使用默认设备）
remote control <plan> <key>

# 指定设备发送指令
remote control --device <name> <plan> <key>
```

---

## 设备 IP 解析逻辑

1. **static 模式**：直接使用配置中的 `ip` 字段连接
2. **dhcp 模式**：
   - 检查 `cached_ip` 是否在 `dhcp_cache_ttl` 有效期内
   - 有效则直接使用缓存 IP
   - 过期或缓存 IP 连接失败，则重新扫描局域网，按 MAC 地址匹配
   - 扫描成功后更新 `cached_ip` 和 `cache_time`

---

## 安装与运行

```bash
# 安装依赖
uv sync

# 运行
uv run remote <subcommand>
```

---

## 当前限制

- 仅支持 IR（红外）模式，不支持 RF（射频）
