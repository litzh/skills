---
name: tieba
description: 百度贴吧数据抓取与查询工具。支持增量拉取指定贴吧的帖子、回复、楼中楼及用户主页信息，数据本地缓存，支持按 IP 归属地、用户名、关键词过滤，可跨贴吧查询。
---

# 百度贴吧查询工具

本工具用于抓取和查询百度贴吧的帖子与用户数据，数据本地缓存，支持跨贴吧查询。

## 运行方式

**必须在 `tieba/` 目录下运行**，缓存文件写入当前目录下的 `.cache/`：

```bash
cd tieba
uv run python tieba.py <子命令> [参数]
```

---

## 子命令

### `fetch` — 拉取贴吧数据

从指定贴吧抓取帖子（主题帖→回复→楼中楼）及涉及用户的主页信息，增量写入本地缓存。

```bash
uv run python tieba.py fetch <贴吧名> [选项]
```

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `fname` | 必填 | 贴吧名称，如 `天堂鸡汤` |
| `-n / --limit` | 30 | 每次拉取的主题帖数量上限 |
| `--sort` | `create` | 排序方式：`create`（发帖时间）/ `reply`（回复时间） |
| `--refresh` | 否 | 忽略最短拉取间隔，强制重新拉取 |

**输出：** 本次拉取摘要（主题帖数、回复数、涉及用户数、最后拉取时间）。

**拉取间隔保护（防止频繁调用被风控）：**
- 同一贴吧：距上次拉取不足 1 小时则跳过
- 同一用户：距上次拉取不足 1 天则跳过
- `--refresh` 可跳过以上限制

**示例：**
```bash
# 拉取「天堂鸡汤」最近50个帖子
uv run python tieba.py fetch 天堂鸡汤 -n 50

# 按回复时间排序，强制刷新
uv run python tieba.py fetch 天堂鸡汤 --sort reply --refresh
```

---

### `query` — 查询用户

从缓存中查询用户，结果按用户组织，每个用户包含基本信息及其发言记录。**不指定 `--fname` 时跨所有已缓存贴吧查询。**

指定 `--fname` 时，会先触发一次增量拉取（受间隔保护）再查询。

```bash
uv run python tieba.py query [选项]
```

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--fname` | 全部 | 限定某个贴吧，不指定则跨所有已缓存贴吧 |
| `-n / --limit` | 30 | 指定 `--fname` 时的拉取数量上限 |
| `--sort` | `create` | 指定 `--fname` 时的排序方式 |
| `--refresh` | 否 | 忽略最短拉取间隔，强制重新拉取 |
| `--days` | 7 | 只显示最近 N 天内有发言的用户，`0` 表示不限制 |
| `--ip` | — | 按 IP 归属地过滤，模糊匹配，如 `北京` |
| `--name` | — | 按用户昵称或用户名过滤，模糊匹配 |
| `--keyword` | — | 按发言内容关键词过滤 |
| `--brief` | 否 | 只显示用户信息和发言条数，不展开每条发言 |
| `--detail` | 否 | 显示每条发言的正文内容（默认只显示一行摘要） |
| `--json` | 否 | 输出 JSON 格式到 stdout |

**示例：**
```bash
# 查询所有缓存贴吧最近7天的活跃用户（简要信息）
uv run python tieba.py query --brief

# 查询「天堂鸡汤」最近3天，显示发言正文
uv run python tieba.py query --fname 天堂鸡汤 --days 3 --detail

# 查找 IP 归属地包含「广东」的用户
uv run python tieba.py query --ip 广东

# 查找发言包含「推荐」的用户，输出 JSON
uv run python tieba.py query --keyword 推荐 --json

# 不限时间，查找特定用户名
uv run python tieba.py query --name 张三 --days 0
```

---

### `clear` — 清除缓存

删除所有本地缓存文件。

```bash
uv run python tieba.py clear
```

---

## 输出格式

### 纯文本（默认）

每个用户一个条目：

```
============================================================
用户昵称 [会员]  https://tieba.baidu.com/home/main?id=xxx
  IP: 广东  注册: 2019-06  性别: 男  等级: Lv12  发帖: 3421  粉丝: 88
  签名: 个性签名内容

  [本吧发言 3 条]
  [回复] 2026-03-10 14:23:01  [天堂鸡汤] 帖子标题  https://tieba.baidu.com/p/xxx
  [楼中楼] 2026-03-09 09:11:44  [天堂鸡汤] 帖子标题  https://tieba.baidu.com/p/xxx

  [主页公开发言 5 条]
  [主页帖] 2026-03-08 20:05:33  [其他贴吧] 帖子标题  https://tieba.baidu.com/p/xxx
```

加 `--detail` 后，每条发言下方会附上正文：

```
  [回复] 2026-03-10 14:23:01  [天堂鸡汤] 帖子标题  https://tieba.baidu.com/p/xxx
    > 发言正文内容摘要...
```

加 `--brief` 后，只显示用户信息和统计：

```
============================================================
用户昵称  https://tieba.baidu.com/home/main?id=xxx
  IP: 广东  注册: 2019-06  性别: 男  等级: Lv12  发帖: 3421  粉丝: 88
  [本吧发言 3 条 / 主页公开发言 5 条]
```

### JSON（`--json`）

输出到 stdout，结构如下：

```json
[
  {
    "user": {
      "user_id": 123456,
      "nick_name": "用户昵称",
      "user_name": "username",
      "portrait": "tb.1.xxx",
      "ip": "广东",
      "register_date": "2019-06",
      "gender": 1,
      "glevel": 12,
      "post_num": 3421,
      "fan_num": 88,
      "follow_num": 50,
      "sign": "个性签名",
      "is_vip": false,
      "is_god": false,
      "is_blocked": false
    },
    "forum_posts": [
      {
        "pid": 987654,
        "tid": 111111,
        "fname": "天堂鸡汤",
        "thread_title": "帖子标题",
        "floor": 3,
        "text": "发言正文",
        "ip": "广东",
        "create_time": 1741234567,
        "type": "post"
      }
    ],
    "homepage_posts": [
      {
        "tid": 222222,
        "fname": "其他贴吧",
        "title": "帖子标题",
        "text": "首楼正文",
        "create_time": 1741100000,
        "type": "homepage"
      }
    ]
  }
]
```

**字段说明：**
- `type`：发言类型，`post`（楼层回复）/ `comment`（楼中楼）/ `homepage`（主页帖）
- `register_date`：由吧龄估算的注册年月，格式 `YYYY-MM`
- `ip`：IP 归属地（楼中楼的 `ip` 为空，从用户信息的 `ip` 字段获取）
- `forum_posts`：本次查询范围内抓到的该用户发言（已去重）
- `homepage_posts`：该用户主页公开的最近发言（跨吧，第1页约10条）

---

## 典型工作流

```bash
# 1. 先拉取数据（可定期执行）
uv run python tieba.py fetch 天堂鸡汤 -n 30

# 2. 查询近期活跃用户概览
uv run python tieba.py query --fname 天堂鸡汤 --brief

# 3. 定向查找可疑用户
uv run python tieba.py query --ip 海外 --days 30

# 4. 导出 JSON 供进一步分析
uv run python tieba.py query --fname 天堂鸡汤 --days 0 --json > users.json
```
