"""磁盘缓存，永久化存储，增量追加，带最短拉取间隔保护"""

import hashlib
import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("TIEBA_CACHE_DIR", Path.home() / ".cache/tieba"))

# 最短拉取间隔（秒）
THREAD_MIN_INTERVAL = 3600    # 帖子 1 小时
USER_MIN_INTERVAL = 86400     # 用户 1 天


def _forum_path(fname: str) -> Path:
    h = hashlib.md5(fname.encode()).hexdigest()
    return CACHE_DIR / f"{h}_forum.json"


def _user_path(user_id: int) -> Path:
    h = hashlib.md5(str(user_id).encode()).hexdigest()
    return CACHE_DIR / f"{h}_user.json"


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(path: Path, data: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── 贴吧帖子缓存 ──────────────────────────────────────────────────────────────

def forum_can_fetch(fname: str, refresh: bool) -> bool:
    """是否允许拉取贴吧数据（未超过最短间隔则跳过）"""
    if refresh:
        return True
    data = _read(_forum_path(fname))
    last = data.get("last_fetch", 0)
    return time.time() - last >= THREAD_MIN_INTERVAL


def forum_load(fname: str) -> dict:
    """加载贴吧缓存，返回 {threads, posts, user_ids, last_fetch}"""
    data = _read(_forum_path(fname))
    return {
        "threads": data.get("threads", {}),   # tid -> thread dict
        "posts": data.get("posts", {}),        # pid -> post dict
        "user_ids": set(data.get("user_ids", [])),
        "last_fetch": data.get("last_fetch", 0),
    }


def forum_save(fname: str, threads: dict, posts: dict, user_ids: set) -> None:
    path = _forum_path(fname)
    _write(path, {
        "last_fetch": time.time(),
        "threads": threads,
        "posts": posts,
        "user_ids": list(user_ids),
    })


# ── 用户缓存 ──────────────────────────────────────────────────────────────────

def user_can_fetch(user_id: int, refresh: bool) -> bool:
    if refresh:
        return True
    data = _read(_user_path(user_id))
    last = data.get("last_fetch", 0)
    return time.time() - last >= USER_MIN_INTERVAL


def user_load(user_id: int) -> dict | None:
    """加载用户缓存，返回 {info, posts, last_fetch} 或 None"""
    data = _read(_user_path(user_id))
    if not data:
        return None
    return data


def user_save(user_id: int, info: dict, posts: dict) -> None:
    """posts: tid -> homepage_thread dict"""
    path = _user_path(user_id)
    _write(path, {
        "last_fetch": time.time(),
        "info": info,
        "posts": posts,
    })


# ── 枚举 ──────────────────────────────────────────────────────────────────────

def all_forum_names() -> list[str]:
    """返回缓存中所有贴吧的名称列表"""
    if not CACHE_DIR.exists():
        return []
    result = []
    for path in CACHE_DIR.glob("*_forum.json"):
        data = _read(path)
        # fname 存在 threads 的任意一条里
        threads = data.get("threads", {})
        if threads:
            fname = next(iter(threads.values())).get("fname", "")
            if fname:
                result.append(fname)
    return result


# ── 清除 ──────────────────────────────────────────────────────────────────────

def cache_clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count
