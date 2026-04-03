---
name: ys7
description: 萤石摄像头直播流访问。内网环境优先使用 RTSP 直连；外网或 RTSP 不可达时，通过萤石开放平台 API 鉴权后获取 HLS 等格式的播放地址。
---

# 萤石摄像头

## 场景一：内网 RTSP 直连（推荐）

适用于与摄像头处于同一局域网的情况，无需鉴权，延迟低，最高效。

参数：
* `username` 用户名，默认为 `admin`
* `password` 密码，默认为设备底部的验证码，环境变量 `YS7_DEVICE_PASSWORD`
* `ip-address` 设备 IP，可从路由器管理页面查看，环境变量 `YS7_DEVICE_IP`

播放地址：
```
rtsp://username:password@ip-address:554/h264/ch1/main/av_stream
```

## 场景二：外网访问（RTSP 不可达时）

适用于无法直连摄像头内网 IP 的情况（如远程访问、RTSP 被防火墙拦截等）。需通过萤石开放平台 API 先鉴权获取 accessToken，再获取播放地址。

### 第一步：获取 accessToken

环境变量：`YS7_APP_KEY`、`YS7_APP_SECRET`

```bash
curl --location --request POST "https://open.ys7.com/api/lapp/token/get?appKey=${YS7_APP_KEY}&appSecret=${YS7_APP_SECRET}"
```

返回值：
```json
{
    "msg": "操作成功!",
    "code": "200",
    "data": {
        "accessToken": "xxxxxxxxx",
        "expireTime": 1773556117948
    }
}
```

### 第二步：获取播放地址

环境变量：`YS7_ACCESS_TOKEN`（上一步获取）、`YS7_DEVICE_SERIAL`（设备序列号）

协议选项（`protocol`）：
* `1` EZOPEN
* `2` HLS（默认，兼容性最好）
* `3` RTMP
* `4` FLV

```bash
curl --location 'https://open.ys7.com/api/lapp/v2/live/address/get' \
    --form "accessToken=\"${YS7_ACCESS_TOKEN}\"" \
    --form "deviceSerial=\"${YS7_DEVICE_SERIAL}\"" \
    --form "protocol=\"2\""
```

返回值：
```json
{
    "msg": "操作成功",
    "code": "200",
    "data": {
        "id": "950764251958661120",
        "url": "https://open.ys7.com/v3/openlive/L32959516_1_1.m3u8?expire=1773038262&id=950764251958661120&t=3a0310d05ecd793a36344ede2eeeac300781d725296a35dab9fb7bda5095c1c0&ev=101",
        "expireTime": "2026-03-09 14:37:42"
    }
}
```

使用返回的 `url` 即可在支持 HLS 的播放器中播放直播流。
