"""输出格式化：纯文本 / JSON"""

import json
from datetime import datetime


def _fmt_time(ts: int) -> str:
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _user_profile_url(portrait: str) -> str:
    return f"https://tieba.baidu.com/home/main?id={portrait}"


def _thread_url(tid: int) -> str:
    return f"https://tieba.baidu.com/p/{tid}"


def _forum_url(fname: str) -> str:
    return f"https://tieba.baidu.com/f?kw={fname}"


# ── 纯文本 ────────────────────────────────────────────────────────────────────

def _post_line(post: dict, detail: bool) -> str:
    ts = _fmt_time(post["create_time"])
    fname = post.get("fname", "")
    thread_title = post.get("thread_title") or post.get("title", "")
    tid = post.get("tid", 0)
    url = _thread_url(tid)
    post_type = post.get("type", "post")
    type_tag = {"comment": "[楼中楼]", "post": "[回复]", "homepage": "[主页帖]"}.get(post_type, "")

    location = f"[{fname}] {thread_title}" if thread_title else f"[{fname}]"
    line = f"  {type_tag} {ts}  {location}  {url}"
    if detail:
        text = post.get("text", "").strip().replace("\n", " ")
        if text:
            line += f"\n    > {text}"
    return line


def format_text(user_view: list[dict], detail: bool = False, brief: bool = False) -> str:
    parts = []
    for entry in user_view:
        u = entry["user"]
        nick = u.get("nick_name") or u.get("user_name") or str(u.get("user_id", ""))
        portrait = u.get("portrait", "")
        url = _user_profile_url(portrait) if portrait else ""
        ip = u.get("ip") or "未知"
        register_date = u.get("register_date") or "未知"
        gender_val = u.get("gender", 0)
        gender = {0: "未知", 1: "男", 2: "女"}.get(gender_val, "未知")
        glevel = u.get("glevel", 0)
        post_num = u.get("post_num", 0)
        fan_num = u.get("fan_num", 0)
        tags = ""
        if u.get("is_vip"):
            tags += " [会员]"
        if u.get("is_god"):
            tags += " [大神]"
        if u.get("is_blocked"):
            tags += " [封禁]"
        sign = u.get("sign", "")

        header = f"{'='*60}\n{nick}{tags}"
        if url:
            header += f"  {url}"
        meta = f"  IP: {ip}  注册: {register_date}  性别: {gender}  等级: Lv{glevel}  发帖: {post_num}  粉丝: {fan_num}"
        if sign:
            meta += f"\n  签名: {sign}"

        parts.append(header)
        parts.append(meta)

        forum_posts = entry["forum_posts"]
        hp_posts = entry["homepage_posts"]

        if not brief:
            if forum_posts:
                parts.append(f"\n  [本吧发言 {len(forum_posts)} 条]")
                for post in forum_posts:
                    parts.append(_post_line(post, detail))

            if hp_posts:
                parts.append(f"\n  [主页公开发言 {len(hp_posts)} 条]")
                for post in hp_posts:
                    parts.append(_post_line(post, detail))
        else:
            total = len(forum_posts) + len(hp_posts)
            if total:
                parts.append(f"  [本吧发言 {len(forum_posts)} 条 / 主页公开发言 {len(hp_posts)} 条]")

        parts.append("")

    return "\n".join(parts)


def format_fetch_summary(summary: dict) -> str:
    fname = summary["fname"]
    last = summary["last_fetch"]
    last_str = _fmt_time(int(last)) if last else "从未"
    url = _forum_url(fname)
    return (
        f"贴吧: {fname}  {url}\n"
        f"主题帖: {summary['thread_count']}  回复/楼中楼: {summary['post_count']}"
        f"  涉及用户: {summary['user_count']}\n"
        f"最后拉取: {last_str}"
    )


# ── JSON ──────────────────────────────────────────────────────────────────────

def format_json(user_view: list[dict]) -> str:
    return json.dumps(user_view, ensure_ascii=False, indent=2)
