# -*- coding: utf-8 -*-
"""
报告输出模块
接受配置、指标、再平衡日志、每日快照，打印完整报告并导出 CSV。
"""

import os
import pandas as pd


def print_report(
    cfg: dict,
    metrics_main: dict,
    metrics_hold: dict,
    rebalance_log: list[dict],
    daily_main: pd.DataFrame,
    daily_hold: pd.DataFrame,
    output_dir: str = '.',
):
    """
    打印回测报告并导出 CSV。

    参数
    ----
    cfg            : 完整配置字典（含 meta / assets / portfolio / strategy）
    metrics_main   : 主策略指标（calc_metrics 返回值）
    metrics_hold   : 买入持有指标
    rebalance_log  : 再平衡记录列表
    daily_main     : 主策略每日快照
    daily_hold     : 买入持有每日快照
    output_dir     : CSV 导出目录
    """
    meta      = cfg.get('meta', {})
    assets    = cfg['assets']
    portfolio = cfg.get('portfolio', {})

    codes      = list(assets.keys())
    names      = {code: assets[code].get('name', code) for code in codes}
    total_cap  = float(portfolio.get('total_capital', 0))
    start_date = meta.get('start', '')
    end_date   = meta.get('end', '')
    port_name  = meta.get('name', '投资组合')

    # 各资产初始资金
    init_values = {code: total_cap * float(assets[code]['weight']) for code in codes}

    _sep = '=' * 62

    print(f'\n{_sep}')
    print(f'  {port_name} 回测报告')
    print(f'  回测区间：{start_date} ~ {end_date}')
    print(f'  初始资金：{total_cap:,.0f} 元')
    print(_sep)

    # ── 一、策略对比汇总 ──────────────────────────────────────────
    print('\n【一、策略对比汇总】')
    col_w = 18
    rows = [
        ('期末总市值(元)', f"{metrics_main['final_value']:,.2f}",     f"{metrics_hold['final_value']:,.2f}"),
        ('总收益率',       _pct(metrics_main['total_return']),         _pct(metrics_hold['total_return'])),
        ('年化收益率',     _pct(metrics_main['annual_return']),        _pct(metrics_hold['annual_return'])),
        ('年化波动率',     _pct(metrics_main['annual_vol']),           _pct(metrics_hold['annual_vol'])),
        ('夏普比率',       f"{metrics_main['sharpe']:.3f}",            f"{metrics_hold['sharpe']:.3f}"),
        ('最大回撤',       _pct(metrics_main['max_drawdown']),         _pct(metrics_hold['max_drawdown'])),
    ]
    strat_label = metrics_main['label']
    print(f"  {'指标':<12} {strat_label:>{col_w}} {'买入持有':>{col_w}}")
    print('  ' + '-' * (12 + col_w * 2 + 4))
    for name, v_main, v_hold in rows:
        print(f"  {name:<12} {v_main:>{col_w}} {v_hold:>{col_w}}")

    # ── 二、再平衡记录 ────────────────────────────────────────────
    print(f'\n【二、再平衡记录（共 {len(rebalance_log)} 次）】')
    if not rebalance_log:
        print('  无再平衡操作')
    else:
        header_names = '  '.join(f"{names[c]:>6}" for c in codes)
        print(f"  {'日期':<12} {'触发原因':<10} 各资产权重（再平衡前）")
        print(f"  {'':12} {'':10} {header_names}")
        print('  ' + '-' * 72)
        for r in rebalance_log:
            w_str = '  '.join(f"{r['before_weights'][c]*100:>5.1f}%" for c in codes)
            print(f"  {r['date']:<12} {r['reason']:<10} {w_str}")
            ops = []
            for c in codes:
                v = r['trades'][c]
                ops.append(f"{names[c]}{'买入' if v >= 0 else '卖出'}{abs(v):,.0f}元")
            print(f"  {'':22} → " + ' | '.join(ops))

    # ── 三、各资产期末表现（主策略）──────────────────────────────
    _print_asset_table(
        '三', f'各资产期末表现（{strat_label}）',
        daily_main, codes, names, init_values
    )

    # ── 四、各资产期末表现（买入持有）────────────────────────────
    _print_asset_table(
        '四', '各资产期末表现（买入持有）',
        daily_hold, codes, names, init_values
    )

    print(f'\n{_sep}')

    # ── CSV 导出 ──────────────────────────────────────────────────
    safe_name = port_name.replace(' ', '_')
    out_path = os.path.join(output_dir, f'backtest_{safe_name}.csv')
    daily_main.to_csv(out_path)
    print(f'\n  每日详细数据已导出：{out_path}')


# ── 内部辅助 ──────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f'{v * 100:.2f}%'


def _print_asset_table(
    section: str,
    title: str,
    daily_df: pd.DataFrame,
    codes: list[str],
    names: dict[str, str],
    init_values: dict[str, float],
):
    print(f'\n【{section}、{title}】')
    last  = daily_df.iloc[-1]
    total = last['total_value']
    print(f"  {'资产':<8} {'期末市值(元)':>14} {'占比':>8} {'单资产收益':>10}")
    print('  ' + '-' * 46)
    for code in codes:
        mv  = last[f'mv_{code}']
        w   = last[f'w_{code}']
        ret = (mv - init_values[code]) / init_values[code]
        print(f"  {names[code]:<8} {mv:>14,.2f} {w*100:>7.1f}% {ret*100:>9.2f}%")
    print(f"  {'合计':<8} {total:>14,.2f} {'100.0%':>8}")
