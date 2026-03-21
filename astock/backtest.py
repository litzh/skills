# -*- coding: utf-8 -*-
"""
投资组合回测入口

用法：
  python backtest.py <配置文件路径> [--start YYYY-MM-DD] [--end YYYY-MM-DD]

示例：
  python backtest.py config/permanent_portfolio.toml
  python backtest.py config/permanent_portfolio.toml --start 2020-01-01 --end 2023-12-31
"""

import sys
import os
import argparse
import tomllib
from datetime import date

import adata
from backtest.data_loader import load_trade_calendar, load_price_data
from backtest.rebalance   import make_strategy, BuyAndHold
from backtest.engine      import run_backtest
from backtest.metrics     import calc_metrics
from backtest.report      import print_report
from backtest.cache       import compute_hash, load as cache_load, save as cache_save


def load_config(path: str) -> tuple[dict, bytes]:
    """返回 (解析后的配置字典, 原始文件字节)"""
    with open(path, 'rb') as f:
        raw = f.read()
    return tomllib.loads(raw.decode()), raw


def resolve_dates(cfg: dict, cli_start: str | None, cli_end: str | None) -> tuple[str, str]:
    """命令行参数优先，其次配置文件，最后兜底默认值"""
    today = date.today().strftime('%Y-%m-%d')
    start = cli_start or cfg.get('meta', {}).get('start') or '1990-01-01'
    end   = cli_end   or cfg.get('meta', {}).get('end')   or today
    # 更新 cfg 以便报告展示正确区间
    cfg.setdefault('meta', {})['start'] = start
    cfg['meta']['end'] = end
    return start, end


def prepare_assets(cfg: dict, total_capital: float) -> dict:
    """
    将 TOML assets 配置扁平化，注入每项资产的 initial_value。
    返回：{ code: {name, weight, is_cash, cash_rate, initial_value} }
    """
    assets = cfg.get('assets', {})
    # 校验权重之和
    total_w = sum(float(v.get('weight', 0)) for v in assets.values())
    if abs(total_w - 1.0) > 1e-6:
        raise ValueError(f"配置文件中资产权重之和为 {total_w:.4f}，应等于 1.0")

    result = {}
    for code, v in assets.items():
        entry = dict(v)
        entry['initial_value'] = total_capital * float(v['weight'])
        result[code] = entry
    return result


def main():
    # ── 命令行解析 ────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description='ETF投资组合回测工具')
    parser.add_argument('config', help='配置文件路径，例如 config/portfolio.toml')
    parser.add_argument('--start', metavar='YYYY-MM-DD', help='回测开始日期（覆盖配置文件）')
    parser.add_argument('--end',   metavar='YYYY-MM-DD', help='回测结束日期（覆盖配置文件）')
    parser.add_argument('--proxy', metavar='HOST:PORT', help='HTTP 代理地址，例如 127.0.0.1:7890')
    args = parser.parse_args()

    if args.proxy:
        adata.proxy(is_proxy=True, ip=args.proxy)
        print(f'[代理] 使用 HTTP 代理：{args.proxy}')

    # ── 加载配置 ──────────────────────────────────────────────────
    cfg, raw_bytes = load_config(args.config)
    total_capital  = float(cfg.get('portfolio', {}).get('total_capital', 1_000_000))
    start, end     = resolve_dates(cfg, args.start, args.end)
    assets         = prepare_assets(cfg, total_capital)

    print(f'配置：{cfg["meta"].get("name", "")}')
    print(f'区间：{start} ~ {end}  |  总资金：{total_capital:,.0f} 元')

    # ── 缓存检查 ──────────────────────────────────────────────────
    digest  = compute_hash(raw_bytes, start, end)
    cached  = cache_load(digest)
    output_dir = os.path.dirname(os.path.abspath(args.config))

    if cached:
        print(f'\n[缓存命中] {digest[:12]}  (创建于 {cached["created_at"]})')
        print_report(cfg, cached['metrics_main'], cached['metrics_hold'],
                     cached['rebalance_log'], cached['daily_main'], cached['daily_hold'],
                     output_dir=output_dir)
        return

    # ── 数据获取 ──────────────────────────────────────────────────
    print('\n[ 1/4 ] 获取交易日历...')
    trade_dates = load_trade_calendar(start, end)
    print(f'        共 {len(trade_dates)} 个交易日，{trade_dates[0]} ~ {trade_dates[-1]}')

    print('\n[ 2/4 ] 获取ETF行情数据...')
    price_df = load_price_data(assets, start, end)
    if not price_df.empty:
        print(f'        价格数据维度：{price_df.shape}')

    # ── 回测 ──────────────────────────────────────────────────────
    print('\n[ 3/4 ] 运行回测...')

    # 主策略
    strategy_main = make_strategy(cfg.get('strategy', {}))
    daily_main, rebalance_log = run_backtest(trade_dates, price_df, assets, strategy_main)

    # 买入持有（固定作为基准对比）
    strategy_hold = BuyAndHold()
    daily_hold, _ = run_backtest(trade_dates, price_df, assets, strategy_hold)

    # ── 报告 ──────────────────────────────────────────────────────
    print('\n[ 4/4 ] 生成报告...')

    # 无风险利率：取现金类资产利率的均值，若无现金资产则用 2%
    cash_rates = [float(v.get('cash_rate', 0.02))
                  for v in assets.values() if v.get('is_cash', False)]
    risk_free = sum(cash_rates) / len(cash_rates) if cash_rates else 0.02

    strategy_label = {
        'threshold_and_periodic': '阈值+定期再平衡',
        'threshold_only':         '阈值再平衡',
        'periodic_only':          '定期再平衡',
        'buy_and_hold':           '买入持有',
    }.get(cfg.get('strategy', {}).get('type', ''), '再平衡策略')

    metrics_main = calc_metrics(daily_main, strategy_label, risk_free)
    metrics_hold = calc_metrics(daily_hold, '买入持有',     risk_free)

    print_report(cfg, metrics_main, metrics_hold, rebalance_log,
                 daily_main, daily_hold, output_dir=output_dir)

    # ── 写入缓存 ──────────────────────────────────────────────────
    cache_path = cache_save(digest, {
        'cfg':           cfg,
        'assets':        assets,
        'daily_main':    daily_main,
        'daily_hold':    daily_hold,
        'rebalance_log': rebalance_log,
        'metrics_main':  metrics_main,
        'metrics_hold':  metrics_hold,
    })
    print(f'\n  回测结果已缓存：{cache_path}')


if __name__ == '__main__':
    main()
