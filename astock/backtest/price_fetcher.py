# -*- coding: utf-8 -*-
"""
实时价格查询模块
复用东方财富前复权日K线接口，取最近一个交易日的收盘价作为当前价格。
"""

from datetime import date, timedelta
from adata.common.utils import requests as adata_req


def fetch_latest_price(code: str) -> tuple[float, str]:
    """
    查询指定代码的最新价格（最近一个交易日收盘价）。

    返回 (price, trade_date)
    若查询失败或无数据，抛出 ValueError。
    """
    today = date.today().strftime('%Y%m%d')
    # 往前取 10 天，确保能覆盖节假日
    lookback = (date.today() - timedelta(days=10)).strftime('%Y%m%d')

    se_cid = 1 if code.startswith('5') or code.startswith('6') else 0
    params = {
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116',
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'klt': '101',
        'fqt': '1',
        'secid': f'{se_cid}.{code}',
        'beg': lookback,
        'end': today,
        '_': '1623766962675',
    }
    try:
        r = adata_req.request('get', 'http://push2his.eastmoney.com/api/qt/stock/kline/get',
                              params=params)
        if not r.text or not r.text.strip():
            raise SystemExit(
                '\n[IP 风控] 东方财富返回空响应，当前 IP 可能已被限流。\n'
                '建议：等待一段时间后重试，或配置代理后再运行。\n'
                '  uv run python rebalance_now.py ... --proxy host:port'
            )
        data_json = r.json()
    except SystemExit:
        raise
    except Exception as e:
        if 'RemoteDisconnected' in str(e) or 'Connection aborted' in str(e):
            raise SystemExit(
                '\n[IP 封锁] 东方财富服务器主动断开连接，当前 IP 可能已被限流。\n'
                '建议：等待一段时间后重试，或配置代理后再运行。\n'
                '  uv run python rebalance_now.py ... --proxy host:port'
            )
        raise ValueError(f"网络请求失败（{code}）：{e}")

    if not data_json.get('data') or not data_json['data'].get('klines'):
        raise ValueError(
            f"无法获取 {code} 的价格数据，请检查代码是否正确或网络是否正常\n"
            f"  如为现金类资产，可在持仓配置中改用 value 字段手动指定当前市值"
        )

    # 取最后一条（最近交易日）
    last_line = data_json['data']['klines'][-1]
    fields = last_line.split(',')
    trade_date = fields[0]          # YYYY-MM-DD
    close_price = float(fields[2])  # 收盘价（前复权）
    return close_price, trade_date


def fetch_prices(codes: list[str]) -> dict[str, tuple[float, str]]:
    """
    批量查询价格。
    返回 { code: (price, trade_date) }
    单个失败时抛出 ValueError（含代码信息）。
    """
    result = {}
    for code in codes:
        result[code] = fetch_latest_price(code)
    return result
