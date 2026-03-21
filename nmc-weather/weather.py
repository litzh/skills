import argparse
import json
import os
import sys
import time

import requests

BASE_URL = "https://www.nmc.cn/rest"
INVALID = 9999
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
CACHE_TTL = 7 * 24 * 3600  # 7 days


def fetch(path):
    resp = requests.get(f"{BASE_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def nmc_value(v):
    """Return None for NMC's 9999 sentinel, otherwise return the value."""
    if v == INVALID or v == "9999":
        return None
    return v


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def _cache_valid():
    if not os.path.exists(CACHE_FILE):
        return False
    return time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL


def load_cache(refresh=False):
    if not refresh and _cache_valid():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return _build_cache()


def _build_cache():
    print("正在更新缓存...", file=sys.stderr)
    regions = fetch("/province/all")
    data = []
    for r in regions:
        cities = fetch(f"/province/{r['code']}")
        data.append({
            "code": r["code"],
            "name": r["name"],
            "cities": [{"code": c["code"], "name": c["city"]} for c in cities],
        })
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("缓存已更新。", file=sys.stderr)
    return data


def get_regions(cache):
    return [{"code": r["code"], "name": r["name"]} for r in cache]


def get_cities(cache, region_code):
    for r in cache:
        if r["code"] == region_code:
            return r["cities"]
    return []


def find_region(cache, *, name=None, code=None):
    for r in cache:
        if code and r["code"] == code:
            return r
        if name and r["name"] == name:
            return r
    return None


def find_cities_by_name(cache, city_name):
    matches = []
    for r in cache:
        for c in r["cities"]:
            if c["name"] == city_name:
                matches.append({"code": c["code"], "name": c["name"], "region": r["name"], "region_code": r["code"]})
    return matches


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list(args):
    cache = load_cache(refresh=args.refresh)

    if args.name is None and args.code is None:
        rows = get_regions(cache)
        if args.format == "json":
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(f"{'名称':<16} 代码")
            print("-" * 28)
            for r in rows:
                print(f"{r['name']:<16} {r['code']}")
        return

    region = find_region(cache, name=args.name, code=args.code)
    if region is None:
        key = f"代码 '{args.code}'" if args.code else f"名称 '{args.name}'"
        print(f"错误: 未找到{key}对应的地区", file=sys.stderr)
        sys.exit(1)

    rows = [{"code": c["code"], "name": c["name"], "region": region["name"]} for c in region["cities"]]

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"地区: {region['name']} ({region['code']})")
        print(f"{'城市':<12} 站点代码")
        print("-" * 26)
        for r in rows:
            print(f"{r['name']:<12} {r['code']}")


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------

def cmd_weather(args):
    if args.name is None and args.code is None:
        print("错误: 请提供 --name <城市名> 或 --code <站点代码>", file=sys.stderr)
        sys.exit(1)

    station_code = args.code

    if station_code is None:
        cache = load_cache(refresh=args.refresh)
        matches = find_cities_by_name(cache, args.name)

        if not matches:
            print(f"错误: 未找到城市 '{args.name}'", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f"错误: 找到多个名为 '{args.name}' 的城市，请使用 --code 指定站点代码:", file=sys.stderr)
            for m in matches:
                print(f"  {m['region']} / {m['name']}  代码: {m['code']}", file=sys.stderr)
            sys.exit(1)

        station_code = matches[0]["code"]

    result = fetch(f"/weather?stationid={station_code}")
    if result.get("code") != 0:
        print(f"错误: API 返回失败: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)

    data = result["data"]
    output = _build_weather(data, station_code)

    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_weather(output)


def _build_weather(data, station_code):
    real = data["real"]
    station = real["station"]
    weather = real["weather"]
    wind = real["wind"]
    sun = real.get("sunriseSunset", {})
    air = data.get("air", {})

    warn = real.get("warn", {})
    alert = nmc_value(warn.get("alert"))

    forecast = []
    for d in data["predict"]["detail"]:
        day_w = d["day"]["weather"]
        night_w = d["night"]["weather"]
        forecast.append({
            "date": d["date"],
            "day": {
                "weather": day_w["info"],
                "temp": int(day_w["temperature"]),
                "wind_direction": d["day"]["wind"]["direct"],
                "wind_power": d["day"]["wind"]["power"],
            },
            "night": {
                "weather": night_w["info"],
                "temp": int(night_w["temperature"]),
                "wind_direction": d["night"]["wind"]["direct"],
                "wind_power": d["night"]["wind"]["power"],
            },
            "precipitation_mm": d["precipitation"],
        })

    return {
        "station": {
            "code": station_code,
            "name": station["city"],
            "region": station["province"],
        },
        "publish_time": real["publish_time"],
        "current": {
            "weather": weather["info"],
            "temperature": weather["temperature"],
            "feels_like": weather["feelst"],
            "humidity_pct": weather["humidity"],
            "wind_direction": wind["direct"],
            "wind_power": wind["power"],
            "wind_speed_ms": wind["speed"],
            "sunrise": nmc_value(sun.get("sunrise")),
            "sunset": nmc_value(sun.get("sunset")),
        },
        "air_quality": {
            "aqi": nmc_value(air.get("aqi")),
            "level": nmc_value(air.get("text")),
        },
        "alert": alert,
        "forecast": forecast,
    }


def _print_weather(w):
    s = w["station"]
    c = w["current"]
    aq = w["air_quality"]

    print(f"# {s['name']} ({s['region']})  [站点: {s['code']}]")
    print(f"更新时间: {w['publish_time']}")
    print()
    print("## 当前实况")
    print(f"天气: {c['weather']}  气温: {c['temperature']}°C (体感 {c['feels_like']}°C)")
    print(f"湿度: {c['humidity_pct']}%  风向: {c['wind_direction']} {c['wind_power']} ({c['wind_speed_ms']} m/s)")
    if c["sunrise"] and c["sunset"]:
        print(f"日出: {c['sunrise'].split()[-1]}  日落: {c['sunset'].split()[-1]}")

    print()
    print("## 空气质量")
    if aq["aqi"] is not None:
        print(f"AQI: {aq['aqi']}  等级: {aq['level']}")
    else:
        print("暂无数据")

    if w["alert"]:
        print()
        print(f"## 预警\n{w['alert']}")

    print()
    print("## 未来7天预报")
    header = f"{'日期':<12}{'白天':<20}{'夜间':<20}{'降水(mm)'}"
    print(header)
    print("-" * 60)
    for d in w["forecast"]:
        day = d["day"]
        night = d["night"]
        day_str = f"{day['weather']} {day['temp']}°C {day['wind_direction']}{day['wind_power']}"
        night_str = f"{night['weather']} {night['temp']}°C {night['wind_direction']}{night['wind_power']}"
        print(f"{d['date']:<12}{day_str:<20}{night_str:<20}{d['precipitation_mm']}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="nmc",
        description="中央气象台天气查询工具",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式 (默认: text)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # nmc list
    list_parser = subparsers.add_parser("list", help="列出地区或城市")
    list_parser.add_argument("--name", metavar="<地区名>", help="按名称精确匹配地区")
    list_parser.add_argument("--code", metavar="<地区代码>", help="按代码精确匹配地区")
    list_parser.add_argument("--refresh", action="store_true", help="强制刷新缓存")

    # nmc weather
    weather_parser = subparsers.add_parser("weather", help="查询城市天气")
    weather_parser.add_argument("--name", metavar="<城市名>", help="按城市名查询")
    weather_parser.add_argument("--code", metavar="<站点代码>", help="按站点代码查询")
    weather_parser.add_argument("--refresh", action="store_true", help="强制刷新缓存")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "weather":
        cmd_weather(args)


if __name__ == "__main__":
    main()
