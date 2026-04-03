"""从百度贴吧抓取数据，增量写入永久缓存"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import aiotieba

from cache import (
    all_forum_names,
    forum_can_fetch, forum_load, forum_save,
    user_can_fetch, user_load, user_save,
)


def _age_to_register_date(age: float) -> str:
    """将吧龄（年）估算为注册时间字符串"""
    if not age:
        return ""
    now = datetime.now(tz=timezone.utc)
    days = int(age * 365.25)
    reg = now.replace(tzinfo=None) - timedelta(days=days)
    return reg.strftime("%Y-%m")


# ── 序列化 ────────────────────────────────────────────────────────────────────

def _ser_thread(t, fname: str) -> dict:
    return {
        "tid": t.tid,
        "title": t.title,
        "fname": fname,
        "fid": t.fid,
        "reply_num": t.reply_num,
        "agree": t.agree,
        "view_num": t.view_num,
        "create_time": t.create_time,
        "author_id": t.author_id,
    }


def _ser_post(p, fname: str, thread_title: str, tid: int) -> dict:
    return {
        "pid": p.pid,
        "tid": tid,
        "fname": fname,
        "thread_title": thread_title,
        "floor": p.floor,
        "text": p.contents.text,
        "user_id": p.user.user_id,
        "user_name": p.user.user_name,
        "nick_name": p.user.nick_name_new,
        "portrait": p.user.portrait,
        "ip": p.user.ip,
        "create_time": p.create_time,
        "type": "post",
    }


def _ser_comment(c, fname: str, thread_title: str) -> dict:
    return {
        "pid": c.pid,
        "tid": c.tid,
        "fname": fname,
        "thread_title": thread_title,
        "floor": c.floor,
        "text": c.contents.text,
        "user_id": c.user.user_id,
        "user_name": c.user.user_name,
        "nick_name": c.user.nick_name_new,
        "portrait": c.user.portrait,
        "ip": "",  # 楼中楼 API 不返回 ip，从用户 homepage 补充
        "create_time": c.create_time,
        "type": "comment",
    }


def _ser_homepage_thread(t, user_id: int) -> dict:
    return {
        "tid": t.tid,
        "pid": t.pid,
        "fname": t.fname,
        "fid": t.fid,
        "title": t.title,
        "text": t.contents.text,
        "reply_num": t.reply_num,
        "agree": t.agree,
        "create_time": t.create_time,
        "user_id": user_id,
        "type": "homepage",
    }


def _ser_user(u) -> dict:
    return {
        "user_id": u.user_id,
        "portrait": u.portrait,
        "user_name": u.user_name,
        "nick_name": u.nick_name_new,
        "register_date": _age_to_register_date(u.age),
        "ip": u.ip,
        "gender": u.gender.value if hasattr(u.gender, "value") else int(u.gender),
        "post_num": u.post_num,
        "fan_num": u.fan_num,
        "follow_num": u.follow_num,
        "sign": u.sign,
        "is_vip": u.is_vip,
        "is_god": u.is_god,
        "is_blocked": u.is_blocked,
        "glevel": u.glevel,
    }


# ── 抓取 ──────────────────────────────────────────────────────────────────────

async def _fetch_forum(client, fname: str, limit: int, sort: aiotieba.ThreadSortType, refresh: bool):
    """增量拉取贴吧帖子数据并写入缓存，返回本次新增的 user_id 集合"""

    cache = forum_load(fname)
    threads: dict = cache["threads"]   # tid -> dict
    posts: dict = cache["posts"]       # pid -> dict
    user_ids: set = cache["user_ids"]

    if not forum_can_fetch(fname, refresh):
        return user_ids

    # 拉主题帖列表
    pn = 1
    fetched = 0
    raw_threads = []
    while fetched < limit:
        batch = await client.get_threads(
            fname,
            pn=pn,
            rn=min(30, limit - fetched),
            sort=sort,
        )
        if not batch:
            break
        for t in batch:
            if t.is_top:
                continue
            raw_threads.append(t)
            fetched += 1
            if fetched >= limit:
                break
        if not batch.has_more:
            break
        pn += 1

    # 增量追加回复和楼中楼
    for thread in raw_threads:
        tid = thread.tid
        if str(tid) not in threads:
            threads[str(tid)] = _ser_thread(thread, fname)

        raw_posts = await client.get_posts(tid)
        for post in raw_posts:
            pid = str(post.pid)
            if pid not in posts:
                posts[pid] = _ser_post(post, fname, thread.title, tid)
            if post.user.user_id:
                user_ids.add(post.user.user_id)

            if post.reply_num == 0:
                continue
            comments = await client.get_comments(post.tid, post.pid)
            for comment in comments:
                cpid = str(comment.pid)
                if cpid not in posts:
                    posts[cpid] = _ser_comment(comment, fname, thread.title)
                if comment.user.user_id:
                    user_ids.add(comment.user.user_id)

    forum_save(fname, threads, posts, user_ids)
    return user_ids


async def _fetch_users(client, user_ids: set[int], refresh: bool):
    """增量拉取用户 homepage，写入缓存"""

    async def fetch_one(uid: int):
        if not user_can_fetch(uid, refresh):
            return
        try:
            hp = await client.get_homepage(uid)
            if not (hp and hp.user and hp.user.user_id):
                return
            info = _ser_user(hp.user)
            # homepage 帖子增量合并（tid 去重）
            cached = user_load(uid)
            existing_posts: dict = cached.get("posts", {}) if cached else {}
            for t in hp:
                tid = str(t.tid)
                if tid not in existing_posts:
                    existing_posts[tid] = _ser_homepage_thread(t, uid)
            user_save(uid, info, existing_posts)
        except Exception:
            pass

    await asyncio.gather(*[fetch_one(uid) for uid in user_ids])


def fetch(
    fname: str,
    limit: int = 30,
    sort_by: str = "create",
    refresh: bool = False,
) -> dict:
    """抓取贴吧数据（增量），返回完整缓存内容供后续使用"""
    sort = (
        aiotieba.ThreadSortType.CREATE
        if sort_by == "create"
        else aiotieba.ThreadSortType.REPLY
    )

    async def _run():
        async with aiotieba.Client() as client:
            user_ids = await _fetch_forum(client, fname, limit, sort, refresh)
            await _fetch_users(client, user_ids, refresh)

    asyncio.run(_run())
    return load(fname)


def load(fname: str) -> dict:
    """从缓存加载贴吧完整数据（不发起网络请求）"""
    cache = forum_load(fname)
    threads = cache["threads"]
    posts = cache["posts"]
    user_ids = cache["user_ids"]

    users: dict[int, dict] = {}
    homepage_posts: dict[int, dict] = {}  # uid -> {tid: post}

    for uid in user_ids:
        cached = user_load(uid)
        if cached and cached.get("info"):
            users[uid] = cached["info"]
            homepage_posts[uid] = cached.get("posts", {})

    return {
        "fname": fname,
        "threads": threads,
        "posts": posts,
        "users": users,
        "homepage_posts": homepage_posts,
    }


# ── 按用户组织 ────────────────────────────────────────────────────────────────

def build_user_view(data: dict, days: int | None = 7) -> list[dict]:
    """
    按用户聚合数据。
    days: 只保留最近 N 天内有发言的用户（None 表示不限制）
    """

    cutoff = (time.time() - days * 86400) if days else 0

    users = data["users"]
    homepage_posts = data["homepage_posts"]

    # 按 user_id 聚合本吧发言（已按 pid 去重）
    forum_posts_by_user: dict[int, list[dict]] = {}
    for post in data["posts"].values():
        uid = post.get("user_id", 0)
        if uid == 0:
            continue
        if post["create_time"] < cutoff:
            continue
        forum_posts_by_user.setdefault(uid, []).append(post)

    # homepage 帖子过滤
    hp_by_user: dict[int, list[dict]] = {}
    for uid, posts_dict in homepage_posts.items():
        filtered = [p for p in posts_dict.values() if p["create_time"] >= cutoff]
        if filtered:
            hp_by_user[uid] = filtered

    all_user_ids = set(forum_posts_by_user) | set(hp_by_user)

    result = []
    for uid in all_user_ids:
        user_info = users.get(uid, {
            "user_id": uid,
            "nick_name": "",
            "user_name": "",
            "portrait": "",
            "register_date": "",
            "ip": "",
            "gender": 0,
            "post_num": 0,
            "fan_num": 0,
            "follow_num": 0,
            "sign": "",
            "is_vip": False,
            "is_god": False,
            "is_blocked": False,
            "glevel": 0,
        })

        forum_posts = sorted(
            forum_posts_by_user.get(uid, []),
            key=lambda p: p["create_time"],
            reverse=True,
        )
        hp_posts = sorted(
            hp_by_user.get(uid, []),
            key=lambda p: p["create_time"],
            reverse=True,
        )

        result.append({
            "user": user_info,
            "forum_posts": forum_posts,
            "homepage_posts": hp_posts,
        })

    def _latest(entry):
        all_p = entry["forum_posts"] + entry["homepage_posts"]
        return max((p["create_time"] for p in all_p), default=0)

    result.sort(key=_latest, reverse=True)
    return result


def load_all(fname_filter: str | None = None) -> dict:
    """从缓存加载所有贴吧数据并合并（不发起网络请求）。
    fname_filter: 指定只加载某个贴吧，None 则合并所有。
    """
    fnames = [fname_filter] if fname_filter else all_forum_names()

    all_posts: dict = {}
    all_user_ids: set = set()

    for fname in fnames:
        cache = forum_load(fname)
        all_posts.update(cache["posts"])
        all_user_ids.update(cache["user_ids"])

    users: dict[int, dict] = {}
    homepage_posts: dict[int, dict] = {}

    for uid in all_user_ids:
        cached = user_load(uid)
        if cached and cached.get("info"):
            users[uid] = cached["info"]
            homepage_posts[uid] = cached.get("posts", {})

    return {
        "posts": all_posts,
        "users": users,
        "homepage_posts": homepage_posts,
    }


def fetch_summary(fname: str) -> dict:
    """返回贴吧缓存的统计摘要"""
    cache = forum_load(fname)
    return {
        "fname": fname,
        "thread_count": len(cache["threads"]),
        "post_count": len(cache["posts"]),
        "user_count": len(cache["user_ids"]),
        "last_fetch": cache["last_fetch"],
    }
