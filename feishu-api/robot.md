# 自定义机器人

机器人ID： FEISHU_ROBOT_ID
机器人密码：FEISHU_ROBOT_SECRET

## 发送消息

```bash
curl -X POST -H "Content-Type: application/json" \
    -d '{"msg_type":"text","content":{"text":"request example"}}' \
        https://open.feishu.cn/open-apis/bot/v2/hook/****
```

## 签名

如果开启了签名，需要进行加密，参考代码：

```python
import hashlib
import base64
import hmac

def gen_sign(timestamp, secret):
    # 拼接timestamp和secret
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()

    # 对结果进行base64处理
    sign = base64.b64encode(hmac_code).decode('utf-8')

    return sign
```

加密后发送格式：

```json
// 开启签名验证后发送文本消息
{
        "timestamp": "1599360473",        // 时间戳。
        "sign": "xxxxxxxxxxxxxxxxxxxxx",  // 得到的签名字符串。
        "msg_type": "text",
        "content": {
                "text": "request example"
        }
}
```


