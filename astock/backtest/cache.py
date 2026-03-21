# -*- coding: utf-8 -*-
"""
回测结果缓存模块
基于「配置文件原始内容 + 最终生效的 start/end」计算 SHA256，
命中缓存则直接读取，否则回测完成后写入。

缓存文件：cache/{hash[:12]}.pkl
缓存内容：{'cfg', 'assets', 'daily_main', 'daily_hold', 'rebalance_log',
           'metrics_main', 'metrics_hold', 'hash', 'created_at'}
"""

import hashlib
import os
import pickle
from datetime import datetime

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache')


def compute_hash(config_bytes: bytes, start: str, end: str) -> str:
    """
    用配置文件原始字节 + 生效的时间范围计算 SHA256。
    任何一项变化都会产生不同的 hash。
    """
    h = hashlib.sha256()
    h.update(config_bytes)
    h.update(start.encode())
    h.update(end.encode())
    return h.hexdigest()


def _cache_path(digest: str) -> str:
    return os.path.join(CACHE_DIR, f'{digest[:12]}.pkl')


def load(digest: str) -> dict | None:
    """
    尝试读取缓存。
    返回缓存字典，未命中返回 None。
    """
    path = _cache_path(digest)
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return pickle.load(f)


def save(digest: str, payload: dict) -> str:
    """
    将回测结果写入缓存文件，返回缓存文件路径。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload['hash']       = digest
    payload['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    path = _cache_path(digest)
    with open(path, 'wb') as f:
        pickle.dump(payload, f)
    return path
