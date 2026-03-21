# -*- coding: utf-8 -*-
"""
数据加载模块
- 交易日历：adata（本地缓存 + 深交所接口），自动合并跨年
- ETF行情：东方财富前复权日K线，修正沪市ETF(5/6开头) secid 映射
"""

import os

import adata
import pandas as pd
from adata.common.utils import requests as adata_req

_KLINE_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache', 'kline')
_KLINE_CACHE_EXT = '.pkl'


def load_trade_calendar(start: str, end: str) -> list[str]:
    """
    获取 [start, end] 范围内的交易日列表（升序）。
    自动按年分批拉取并合并。
    """
    start_year = int(start[:4])
    end_year   = int(end[:4])
    frames = []
    for year in range(start_year, end_year + 1):
        df = adata.stock.info.trade_calendar(year=year)
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df[(all_df['trade_date'] >= start) & (all_df['trade_date'] <= end)]
    all_df = all_df[all_df['trade_status'] == 1]
    return sorted(all_df['trade_date'].tolist())


def _fetch_east_kline_remote(code: str, start: str, end: str) -> pd.DataFrame:
    """从东方财富拉取前复权日K线，返回列：trade_date, close"""
    from requests.exceptions import ConnectionError as RequestsConnectionError
    se_cid = 1 if code.startswith('5') or code.startswith('6') else 0
    params = {
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116',
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'klt': '101',
        'fqt': '1',
        'secid': f'{se_cid}.{code}',
        'beg': start.replace('-', ''),
        'end': end.replace('-', ''),
        '_': '1623766962675',
    }
    try:
        r = adata_req.request('get', 'http://push2his.eastmoney.com/api/qt/stock/kline/get',
                              params=params)
    except RequestsConnectionError as e:
        if 'RemoteDisconnected' in str(e) or 'Connection aborted' in str(e):
            raise SystemExit(
                '\n[IP 封锁] 东方财富服务器主动断开连接，当前 IP 可能已被限流。\n'
                '建议：等待一段时间后重试，或配置代理后再运行。\n'
                '  adata.proxy(is_proxy=True, ip="host:port")'
            )
        raise
    if not r.text or not r.text.strip():
        raise SystemExit(
            '\n[IP 风控] 东方财富返回空响应，当前 IP 可能已被限流。\n'
            '建议：等待一段时间后重试，或配置代理后再运行。\n'
            '  uv run python backtest.py config/portfolio.toml --proxy host:port'
        )
    data_json = r.json()
    if not data_json.get('data') or not data_json['data'].get('klines'):
        return pd.DataFrame(columns=['trade_date', 'close'])
    lines = data_json['data']['klines']
    rows = [item.split(',') for item in lines]
    df = pd.DataFrame(rows, columns=[
        'trade_date', 'open', 'close', 'high', 'low',
        'volume', 'amount', '_', 'change_pct', 'change', 'turnover'
    ])
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
    df['close'] = df['close'].astype(float)
    return df[['trade_date', 'close']]


def _fetch_east_kline(code: str, start: str, end: str) -> pd.DataFrame:
    """
    东方财富前复权日K线，带本地增量缓存。
    缓存文件：cache/kline/{code}.parquet，存全量历史数据。
    每次运行只拉取本地缺失的增量部分，历史数据永不重复请求。
    返回列：trade_date, close
    """
    import pickle
    os.makedirs(_KLINE_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_KLINE_CACHE_DIR, f'{code}{_KLINE_CACHE_EXT}')

    # 读取本地缓存
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            cached_df = pickle.load(f)
        latest_cached = cached_df['trade_date'].max()
    else:
        cached_df = pd.DataFrame(columns=['trade_date', 'close'])
        latest_cached = None

    # 确定需要拉取的范围
    today = pd.Timestamp.now().strftime('%Y-%m-%d')
    fetch_start = latest_cached if latest_cached else '19900101'

    if latest_cached and latest_cached >= today:
        # 缓存已是最新，无需请求
        new_df = pd.DataFrame(columns=['trade_date', 'close'])
    else:
        new_df = _fetch_east_kline_remote(code, fetch_start, today)

    # 合并并去重，写回缓存
    if not new_df.empty:
        combined = pd.concat([cached_df, new_df]).drop_duplicates('trade_date').sort_values('trade_date')
        with open(cache_path, 'wb') as f:
            pickle.dump(combined, f)
        cached_df = combined

    # 按请求区间切片返回
    if cached_df.empty:
        return pd.DataFrame(columns=['trade_date', 'close'])
    return cached_df[(cached_df['trade_date'] >= start) & (cached_df['trade_date'] <= end)].reset_index(drop=True)


def load_price_data(assets: dict, start: str, end: str) -> pd.DataFrame:
    """
    获取所有非现金资产的前复权收盘价，返回宽表。
    index = trade_date (str, 'YYYY-MM-DD')
    columns = 各资产代码
    停牌/缺失日用前值填充。

    assets: {code: {name, weight, is_cash, ...}}
    """
    frames = []
    for code, cfg in assets.items():
        if cfg.get('is_cash', False):
            continue
        name = cfg.get('name', code)
        print(f"  获取 {name}({code}) 行情...")
        df = _fetch_east_kline(code, start, end)
        if df.empty:
            raise ValueError(f"无法获取 {code}({name}) 的行情数据，请检查代码或网络")
        df = df.rename(columns={'close': code}).set_index('trade_date')
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    price_df = pd.concat(frames, axis=1).sort_index().ffill()
    return price_df
