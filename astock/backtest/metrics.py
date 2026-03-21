# -*- coding: utf-8 -*-
"""
指标计算模块（纯函数，无副作用）
"""

import numpy as np
import pandas as pd


def calc_metrics(daily_df: pd.DataFrame, label: str, risk_free_rate: float = 0.02) -> dict:
    """
    计算回测绩效指标。

    参数
    ----
    daily_df        : 回测引擎输出的每日快照，必须含 total_value 列
    label           : 策略标签（用于报告展示）
    risk_free_rate  : 无风险利率（年化），用于夏普比率计算

    返回
    ----
    指标字典，所有数值字段均保留原始浮点，格式化由 report 层负责
    """
    values: pd.Series = daily_df['total_value'].astype(float)
    n_days = len(values)

    # 总收益率
    total_return = (values.iloc[-1] - values.iloc[0]) / values.iloc[0]

    # 年化收益率（按交易日数折算，252天/年）
    annual_return = (1 + total_return) ** (252 / n_days) - 1

    # 日收益率序列
    daily_ret = values.pct_change().dropna()

    # 年化波动率
    annual_vol = daily_ret.std() * np.sqrt(252)

    # 夏普比率
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0.0

    # 最大回撤
    cummax = values.cummax()
    drawdown = (values - cummax) / cummax
    max_drawdown = drawdown.min()

    return {
        'label':        label,
        'final_value':  round(float(values.iloc[-1]), 2),
        'total_return': total_return,
        'annual_return': annual_return,
        'annual_vol':   annual_vol,
        'sharpe':       sharpe,
        'max_drawdown': max_drawdown,
    }
