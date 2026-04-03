---
name: caldav-calendar
description: 使用 vdirsyncer + khal 同步和查询 CalDAV 日历（iCloud、Google、Fastmail、Nextcloud 等）。适用于 Linux。
metadata: {"clawdbot":{"emoji":"📅","os":["linux"],"requires":{"bins":["vdirsyncer","khal"]},"install":[{"id":"apt","kind":"apt","packages":["vdirsyncer","khal"],"bins":["vdirsyncer","khal"],"label":"Install vdirsyncer + khal via apt"}]}}
---

# CalDAV 日历（vdirsyncer + khal）

**vdirsyncer** 将 CalDAV 日历同步为本地 `.ics` 文件，**khal** 负责读写这些文件。

## 先同步

查询前或修改后，务必先同步：
```bash
vdirsyncer sync
```

## 查看日程

```bash
khal list                        # 今天
khal list today 7d               # 未来7天
khal list tomorrow               # 明天
khal list 2026-01-15 2026-01-20  # 指定日期范围
khal list -a Work today          # 指定日历
```

## 搜索

```bash
khal search "会议"
khal search "牙医" --format "{start-date} {title}"
```

## 创建日程

```bash
khal new 2026-01-15 10:00 11:00 "会议标题"
khal new 2026-01-15 "全天事项"
khal new tomorrow 14:00 15:30 "通话" -a Work
khal new 2026-01-15 10:00 11:00 "带备注的事项" :: 备注内容写在这里
```

创建后同步以推送变更：
```bash
vdirsyncer sync
```

## 编辑日程（交互式）

`khal edit` 为交互式操作，需要 TTY。自动化场景请使用 tmux：

```bash
khal edit "搜索词"
khal edit -a 日历名称 "搜索词"
khal edit --show-past "历史事项"
```

菜单选项：
- `s` → 编辑标题
- `d` → 编辑描述
- `t` → 编辑时间范围
- `l` → 编辑地点
- `D` → 删除事项
- `n` → 跳过（保存并匹配下一条）
- `q` → 退出

编辑后同步：
```bash
vdirsyncer sync
```

## 删除日程

使用 `khal edit`，然后按 `D` 删除。

## 输出格式

用于脚本处理：
```bash
khal list --format "{start-date} {start-time}-{end-time} {title}" today 7d
khal list --format "{uid} | {title} | {calendar}" today
```

可用占位符：`{title}`、`{description}`、`{start}`、`{end}`、`{start-date}`、`{start-time}`、`{end-date}`、`{end-time}`、`{location}`、`{calendar}`、`{uid}`

## 缓存

khal 将事件缓存于 `~/.local/share/khal/khal.db`。若同步后数据仍显示过期：
```bash
rm ~/.local/share/khal/khal.db
```

## 初始配置

### 1. 配置 vdirsyncer（`~/.config/vdirsyncer/config`）

以 iCloud 为例：
```ini
[general]
status_path = "~/.local/share/vdirsyncer/status/"

[pair icloud_calendar]
a = "icloud_remote"
b = "icloud_local"
collections = ["from a", "from b"]
conflict_resolution = "a wins"

[storage icloud_remote]
type = "caldav"
url = "https://caldav.icloud.com/"
username = "your@icloud.com"
password.fetch = ["command", "cat", "~/.config/vdirsyncer/icloud_password"]

[storage icloud_local]
type = "filesystem"
path = "~/.local/share/vdirsyncer/calendars/"
fileext = ".ics"
```

各服务商地址：
- iCloud：`https://caldav.icloud.com/`
- Google：使用 `google_calendar` 存储类型
- Fastmail：`https://caldav.fastmail.com/dav/calendars/user/EMAIL/`
- Nextcloud：`https://YOUR.CLOUD/remote.php/dav/calendars/USERNAME/`

### 2. 配置 khal（`~/.config/khal/config`）

```ini
[calendars]
[[my_calendars]]
path = ~/.local/share/vdirsyncer/calendars/*
type = discover

[default]
default_calendar = Home
highlight_event_days = True

[locale]
timeformat = %H:%M
dateformat = %Y-%m-%d
```

### 3. 发现并同步

```bash
vdirsyncer discover   # 仅首次执行
vdirsyncer sync
```
