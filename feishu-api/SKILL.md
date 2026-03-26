---
name: feishu-api
description: 飞书开放平台 API 工具集。支持通过邮箱或手机号查询飞书用户的 open_id，以及通过自定义机器人发送文本消息（支持 @ 用户）。
---

# 飞书 API 工具集

封装飞书开放平台常用接口，供 AI 直接调用。

环境变量（已在环境中配置）：
- `FEISHU_APP_ID` 配置文件 `channels.feishu.appId`
- `FEISHU_APP_SECRET` 配置文件 `channels.feishu.appSecret`

---

## 查询用户 open_id

API 文档：https://open.feishu.cn/document/server-docs/contact-v3/user/batch_get_id

通过邮箱或手机号批量查询飞书用户的 `open_id`。

```bash
# 按邮箱查询
uv run scripts/batch_get_id.py --emails user@example.com

# 批量查询多个邮箱
uv run scripts/batch_get_id.py --emails user1@example.com user2@example.com

# 按手机号查询
uv run scripts/batch_get_id.py --mobiles 13800138000
```

返回值：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "user_list": [
      {
        "user_id": "ou_xxx",
        "email": "user@example.com"
      }
    ]
  }
}
```

字段说明：
- `user_id`：即 `open_id`，格式为 `ou_` 开头
- 查询不到的用户不会出现在 `user_list` 中，不会报错

---

## 自定义机器人发送消息

通过飞书自定义机器人 Webhook 发送文本消息（已启用签名验证）。

环境变量：
* `FEISHU_ROBOT_ID` 
* `FEISHU_ROBOT_SECRET` 

```bash
# 发送普通消息
uv run scripts/robot_send.py "消息内容"

# @ 单个用户
uv run scripts/robot_send.py "消息内容" --at <open_id>

# @ 多个用户
uv run scripts/robot_send.py "消息内容" --at <open_id1> <open_id2>
```

返回值：

```json
{
  "code": 0,
  "msg": "success"
}
```
