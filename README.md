# OpenClaw Skills

个人 AI Agent skill 仓库，供 [OpenClaw](https://clawhub.ai) 调用。

每个 skill 是一个独立目录，包含 `SKILL.md`（AI 调用说明）和可选的 Python 脚本。脚本均通过 `uv run` 执行，无需手动安装依赖。

---

## Skills

### 日常工具

| Skill | 描述 |
|-------|------|
| [`diary`](./diary/) | 两阶段日记工作流：实时记录碎片内容，定期生成正式日记写入 Obsidian |
| [`health`](./health/) | 解析 iPhone Health 快捷指令导出的 JSON，输出睡眠结构、HRV、心率、活动能量等健康数据摘要 |
| [`nmc-weather`](./nmc-weather/) | 中央气象台天气查询，支持实况、7天预报、空气质量、气象预警 |
| [`tophub`](./tophub/) | 全网实时热点话题聚合，来自 tophub.today，按报道数量排序 |
| [`ys7`](./ys7/) | 萤石摄像头直播流访问，内网 RTSP 直连或外网 HLS 鉴权播放 |

### 效率与协作

| Skill | 描述 |
|-------|------|
| [`feishu-api`](./feishu-api/) | 飞书 API 工具集：批量查询用户 open_id，通过自定义机器人发送消息（支持 @ 用户） |
| [`remote`](./remote/) | Broadlink 红外遥控器 CLI，管理设备和红外方案，发送遥控指令 |

### 数据与分析

| Skill | 描述 |
|-------|------|
| [`astock`](./astock/) | A 股 ETF 投资组合回测与再平衡工具，支持阈值+定期策略，对比买入持有基准 |
| [`tieba`](./tieba/) | 百度贴吧数据抓取，增量缓存，支持按 IP 归属地、用户名、关键词过滤查询 |

---

## 第三方 Skills

| Skill | 描述 |
|-------|------|
| [`playwright-cli`](https://github.com/microsoft/playwright-cli) | 浏览器自动化，网页交互、截图、数据提取 |
| [`caldav-calendar`](https://clawhub.ai/Asleep123/caldav-calendar) | CalDAV 日历同步与查询（iCloud、Google、Nextcloud 等） |

---

## 结构约定

```
skill-name/
├── SKILL.md          # AI 调用说明（frontmatter + 场景文档）
├── pyproject.toml    # Python 依赖（uv 管理，package = false）
├── script.py         # 主入口脚本（uv run script.py）
└── ...
```

- `SKILL.md` frontmatter 包含 `name`、`description`，供 OpenClaw 索引
- 所有脚本通过 `uv run` 执行，不需要手动创建虚拟环境
- 敏感配置（含设备信息、密钥）通过环境变量注入，不提交到版本库
