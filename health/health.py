#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
iPhone Health JSON 数据解析
用法:
  uv run python health.py path/to/metric.json
  uv run python health.py -d path/to/dir
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def fmt_hours(hours: float) -> str:
    total_min = round(hours * 60)
    h, m = divmod(total_min, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def render_sleep(data: list[dict]) -> str:
    segments = [d for d in data if "start" in d and "end" in d]
    if not segments:
        return "  无有效数据"

    t_start = parse_dt(segments[0]["start"])
    t_end = parse_dt(segments[-1]["end"])
    total_h = (t_end - t_start).total_seconds() / 3600

    stage_totals: dict[str, float] = {}
    for seg in segments:
        v = seg.get("value", "未知")
        stage_totals[v] = stage_totals.get(v, 0) + float(seg["qty"])

    lines = [
        f"  入睡: {t_start.strftime('%H:%M')}  起床: {t_end.strftime('%H:%M')}  总时长: {fmt_hours(total_h)}",
    ]
    order = ["核心", "深度", "快速动眼期", "清醒", "InBed"]
    for stage in order + [s for s in stage_totals if s not in order]:
        if stage in stage_totals:
            dur = stage_totals[stage]
            pct = dur / total_h * 100
            lines.append(f"  {stage}: {fmt_hours(dur)} ({pct:.0f}%)")

    # 睡眠结构序列：先合并连续同类段，再丢弃 < 5m 的碎片后二次合并
    def merge_consecutive(segs: list[tuple[str, int]]) -> list[tuple[str, int]]:
        result: list[tuple[str, int]] = []
        for v, d in segs:
            if result and result[-1][0] == v:
                result[-1] = (v, result[-1][1] + d)
            else:
                result.append((v, d))
        return result

    raw_seq = [(seg.get("value", "?"), round(float(seg["qty"]) * 60)) for seg in segments]
    merged = merge_consecutive(raw_seq)
    filtered = [(v, d) for v, d in merged if d >= 5]
    final_seq = merge_consecutive(filtered)
    seq_str = " → ".join(f"{v}({d}m)" for v, d in final_seq)
    lines.append(f"  结构序列: {seq_str}")

    return "\n".join(lines)


def render_hrv(data: list[dict]) -> str:
    if not data:
        return "  无数据"
    values = [d["qty"] for d in data]
    times = [parse_dt(d["date"]).strftime("%H:%M") for d in data]
    avg = sum(values) / len(values)
    lines = [f"  均值: {avg:.1f} ms  范围: {min(values):.1f}–{max(values):.1f} ms  测量次数: {len(values)}"]
    for t, v in zip(times, values):
        lines.append(f"  {t}  {v:.1f} ms")
    return "\n".join(lines)


def render_single(data: list[dict], units: str, unit_sys: str = "cn") -> str:
    if not data:
        return "  无数据"
    lines = []
    for d in data:
        date = parse_dt(d["date"]).strftime("%Y-%m-%d")
        qty = d["qty"]
        if units == "kJ" and unit_sys == "cn":
            kcal = qty / 4.184
            lines.append(f"  {date}: {kcal:.0f} 千卡")
        elif units == "min" and unit_sys == "cn":
            lines.append(f"  {date}: {qty:.0f} 分钟")
        else:
            lines.append(f"  {date}: {qty:.1f} {units}")
    return "\n".join(lines)


def render_generic(units: str, data: list[dict]) -> str:
    if not data:
        return "  无数据"
    values = [d["qty"] for d in data if "qty" in d]
    if not values:
        return "  无数值数据"
    avg = sum(values) / len(values)
    return f"  数据点: {len(values)}  均值: {avg:.2f} {units}  范围: {min(values):.2f}–{max(values):.2f}"


METRIC_NAMES = {
    "sleep_analysis": "睡眠分析",
    "heart_rate_variability": "心率变异性 (HRV)",
    "resting_heart_rate": "静息心率",
    "active_energy": "活动能量",
    "time_in_daylight": "日光暴露时间",
}


def render_metric(name: str, units: str, data: list[dict], unit_sys: str = "cn") -> str:
    if name == "sleep_analysis":
        return render_sleep(data)
    if name == "heart_rate_variability":
        return render_hrv(data)
    if name in ("resting_heart_rate", "active_energy", "time_in_daylight"):
        return render_single(data, units, unit_sys)
    return render_generic(units, data)


def parse_file(path: Path, unit_sys: str = "cn") -> str:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    metrics = raw.get("data", {}).get("metrics", [])
    if not metrics:
        return f"[{path.name}] 未找到 metrics 数据"

    output = []
    for metric in metrics:
        name = metric.get("name", "unknown")
        units = metric.get("units", "")
        data = metric.get("data", [])
        display = METRIC_NAMES.get(name, name)
        output.append(f"[{display}]")
        output.append(render_metric(name, units, data, unit_sys))

    return "\n".join(output)


def parse_dir(dirpath: Path, unit_sys: str = "cn") -> str:
    files = sorted(dirpath.glob("*.json"))
    if not files:
        return f"目录 {dirpath} 中没有找到 JSON 文件"
    return "\n\n".join(parse_file(f, unit_sys) for f in files)


def main():
    parser = argparse.ArgumentParser(description="解析 iPhone Health 导出 JSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("file", nargs="?", help="单个 JSON 文件路径")
    group.add_argument("-d", "--dir", help="包含多个 JSON 文件的目录")
    parser.add_argument(
        "--unit",
        choices=["si", "cn"],
        default="cn",
        help="单位制：cn=习惯单位（千卡、分钟等），si=国际单位（kJ、min 等），默认 cn",
    )
    args = parser.parse_args()

    if args.dir:
        print(parse_dir(Path(args.dir), args.unit))
    else:
        print(parse_file(Path(args.file), args.unit))


if __name__ == "__main__":
    main()
