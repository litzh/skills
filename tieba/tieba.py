#!/usr/bin/env python3
"""百度贴吧命令行查询工具

用法:
  tieba.py fetch <贴吧名> [选项]   拉取并缓存数据
  tieba.py query <贴吧名> [选项]   按用户查询（含时间过滤）
  tieba.py clear                   清除所有缓存
"""

import argparse
import sys

from cache import cache_clear
from fetcher import fetch, load_all, build_user_view, fetch_summary
from formatter import format_text, format_json, format_fetch_summary


def cmd_fetch(args):
    print(f"正在抓取 [{args.fname}]...", file=sys.stderr)
    fetch(
        fname=args.fname,
        limit=args.limit,
        sort_by=args.sort,
        refresh=args.refresh,
    )
    print(format_fetch_summary(fetch_summary(args.fname)))


def cmd_query(args):
    # 若指定了 --fname，触发增量拉取（受间隔保护）
    if args.fname:
        fetch(
            fname=args.fname,
            limit=args.limit,
            sort_by=args.sort,
            refresh=args.refresh,
        )
    data = load_all(fname_filter=args.fname)
    user_view = build_user_view(data, days=args.days)

    # 过滤
    if args.ip:
        ip_filter = args.ip.lower()
        user_view = [
            e for e in user_view
            if ip_filter in (e["user"].get("ip") or "").lower()
        ]
    if args.name:
        name_filter = args.name.lower()
        user_view = [
            e for e in user_view
            if name_filter in (e["user"].get("nick_name") or "").lower()
            or name_filter in (e["user"].get("user_name") or "").lower()
        ]
    if args.keyword:
        kw = args.keyword.lower()
        filtered = []
        for entry in user_view:
            fp = [p for p in entry["forum_posts"] if kw in (p.get("text") or "").lower()]
            hp = [p for p in entry["homepage_posts"]
                  if kw in (p.get("text") or "").lower()
                  or kw in (p.get("title") or "").lower()]
            if fp or hp:
                filtered.append({**entry, "forum_posts": fp, "homepage_posts": hp})
        user_view = filtered

    if not user_view:
        print("没有符合条件的用户。")
        return

    if args.json:
        print(format_json(user_view))
    else:
        print(format_text(user_view, detail=args.detail, brief=args.brief))


def cmd_clear(args):
    count = cache_clear()
    print(f"已清除 {count} 个缓存文件。")


def main():
    parser = argparse.ArgumentParser(
        prog="tieba.py",
        description="百度贴吧命令行查询工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── fetch ──
    p_fetch = sub.add_parser("fetch", help="增量拉取贴吧数据并缓存，输出摘要")
    p_fetch.add_argument("fname", help="贴吧名称")
    p_fetch.add_argument("-n", "--limit", type=int, default=30,
                         help="每次拉取的主题帖数量上限（默认30）")
    p_fetch.add_argument("--sort", choices=["create", "reply"], default="create",
                         help="排序方式：create 发帖时间 / reply 回复时间（默认 create）")
    p_fetch.add_argument("--refresh", action="store_true",
                         help="忽略最短间隔限制，强制重新拉取")
    p_fetch.set_defaults(func=cmd_fetch)

    # ── query ──
    p_query = sub.add_parser("query", help="跨贴吧查询用户信息（按用户组织）")
    p_query.add_argument("--fname", default=None,
                         help="限定贴吧名称（不指定则查询所有已缓存贴吧）")
    p_query.add_argument("-n", "--limit", type=int, default=30,
                         help="指定 --fname 时，每次拉取的主题帖数量上限（默认30）")
    p_query.add_argument("--sort", choices=["create", "reply"], default="create",
                         help="指定 --fname 时的排序方式（默认 create）")
    p_query.add_argument("--refresh", action="store_true",
                         help="忽略最短间隔限制，强制重新拉取")
    p_query.add_argument("--days", type=int, default=7,
                         help="只显示最近 N 天内有发言的用户（默认7，0表示不限制）")
    p_query.add_argument("--ip", help="按 IP 归属地过滤（模糊匹配）")
    p_query.add_argument("--name", help="按用户昵称/用户名过滤（模糊匹配）")
    p_query.add_argument("--keyword", help="按发言关键词过滤")
    p_query.add_argument("--brief", action="store_true",
                         help="只显示用户信息，不显示回帖记录")
    p_query.add_argument("--detail", action="store_true",
                         help="显示发言正文内容（与 --brief 互斥）")
    p_query.add_argument("--json", action="store_true",
                         help="输出 JSON 格式到 stdout")
    p_query.set_defaults(func=cmd_query)

    # ── clear ──
    p_clear = sub.add_parser("clear", help="清除所有本地缓存")
    p_clear.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
