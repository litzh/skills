# 中央气象台 NMC


## 查询省份列表

* 请求

```
curl 'https://www.nmc.cn/rest/province/all'
```

* 响应例子

```json
[
    {
        "code": "ABJ",
        "name": "北京市",
        "url": "/publish/forecast/ABJ.html"
    }
]
```

## 查询城市列表

* 请求

```
curl 'https://www.nmc.cn/rest/province/:province_code'
```

* 请求例子

```
curl 'https://www.nmc.cn/rest/province/ABJ'
```

* 响应例子

```json
[
    {
        "code": "Wqsps",
        "province": "北京市",
        "city": "北京",
        "url": "/publish/forecast/ABJ/beijing.html"
    },
    {
        "code": "niStC",
        "province": "北京市",
        "city": "昌平",
        "url": "/publish/forecast/ABJ/changping.html"
    }
]
```

## 查询制定气象站的天气

* 请求

```
curl 'https://www.nmc.cn/rest/weather?stationid=:stationid'
```

* 请求例子

```
https://www.nmc.cn/rest/weather?stationid=Wqsps
```

* 返回

```json
{
    "msg": "success",
    "code": 0,
    "data": {
        "real": {},
        "predict": {},
        "air": {},
        "tempchart": [],
        "passedchart": [],
        "climate": {},
        "radar": {}
    }
}
```

