# -*- coding: utf-8 -*-
"""
回测引擎
完全无全局变量，所有参数通过入参传入。
"""

import pandas as pd
from .rebalance import RebalanceStrategy, BuyAndHold


def run_backtest(
    trade_dates: list[str],
    price_df: pd.DataFrame,
    assets: dict,
    strategy: RebalanceStrategy,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    运行一次回测。

    参数
    ----
    trade_dates : 交易日列表（升序字符串）
    price_df    : 宽表，index=trade_date, columns=非现金资产代码，值为前复权收盘价
    assets      : 资产配置字典
                  { code: {name, weight, is_cash, cash_rate(可选), ...} }
    strategy    : 再平衡策略实例

    返回
    ----
    daily_df      : 每日快照 DataFrame，index=trade_date
                    列：total_value, mv_{code}, w_{code}
    rebalance_log : 再平衡记录列表
                    每条：{date, reason, before_weights, trades}
    """
    # ── 预计算（定期日期集合等）──
    strategy.prepare(trade_dates)

    # ── 从配置中提取常用字段 ──
    codes       = list(assets.keys())
    target_w    = {code: float(cfg['weight']) for code, cfg in assets.items()}
    is_cash     = {code: cfg.get('is_cash', False) for code, cfg in assets.items()}
    cash_rates  = {code: float(cfg.get('cash_rate', 0.0))
                   for code, cfg in assets.items() if cfg.get('is_cash', False)}

    # 总资金从 price_df 外部传入 assets 配置里没有，需要在调用处算好后传进来
    # 这里 holdings 初始值由调用方通过 assets[code]['initial_value'] 注入
    holdings: dict[str, float] = {}
    for code, cfg in assets.items():
        if is_cash[code]:
            holdings[code] = float(cfg['initial_value'])
        else:
            first_date = trade_dates[0]
            price = price_df.loc[first_date, code]
            holdings[code] = float(cfg['initial_value']) / price

    rebalance_log: list[dict] = []
    daily_records: list[dict] = []

    # ── 逐日模拟 ──
    for i, today in enumerate(trade_dates):
        is_first_day = (i == 0)

        # 1. 更新现金市值（复利，首日不计息）
        if not is_first_day:
            for code in codes:
                if is_cash[code]:
                    rate = cash_rates[code]
                    daily_rate = (1 + rate) ** (1 / 252) - 1
                    holdings[code] *= (1 + daily_rate)

        # 2. 计算各资产市值
        market_values: dict[str, float] = {}
        for code in codes:
            if is_cash[code]:
                market_values[code] = holdings[code]
            elif today in price_df.index:
                market_values[code] = holdings[code] * price_df.loc[today, code]
            else:
                # 数据缺失：沿用上一条记录的市值
                market_values[code] = daily_records[-1][f'mv_{code}'] if daily_records else float(assets[code]['initial_value'])

        total_value = sum(market_values.values())
        weights = {code: market_values[code] / total_value for code in codes}

        # 3. 再平衡判断
        triggered, reason = strategy.should_rebalance(today, weights, target_w, is_first_day)
        if triggered:
            before_weights = weights.copy()
            trades: dict[str, float] = {}

            for code in codes:
                target_value = total_value * target_w[code]
                diff = target_value - market_values[code]
                trades[code] = diff   # 正=买入，负=卖出
                if is_cash[code]:
                    holdings[code] = target_value
                else:
                    price = price_df.loc[today, code] if today in price_df.index \
                            else price_df.iloc[price_df.index.get_loc(today) - 1][code]
                    holdings[code] = target_value / float(price)

            # 再平衡后权重恢复目标值
            weights = target_w.copy()

            rebalance_log.append({
                'date':           today,
                'reason':         reason,
                'before_weights': before_weights,
                'trades':         trades,
            })

        # 4. 记录当日快照
        record: dict = {'trade_date': today, 'total_value': total_value}
        for code in codes:
            record[f'mv_{code}'] = market_values[code]
            record[f'w_{code}']  = weights[code]
        daily_records.append(record)

    daily_df = pd.DataFrame(daily_records).set_index('trade_date')
    return daily_df, rebalance_log
