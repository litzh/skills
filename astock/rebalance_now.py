# -*- coding: utf-8 -*-
"""
持仓实时再平衡分析工具

用法：
  python rebalance_now.py <持仓配置> <策略配置> [--min-trade N] [--force]

示例：
  python rebalance_now.py config/holdings.toml config/permanent_portfolio.toml
  python rebalance_now.py config/holdings.toml config/permanent_portfolio.toml --force
  python rebalance_now.py config/holdings.toml config/permanent_portfolio.toml --min-trade 500
"""

import sys
import os
import argparse
import tomllib
import math
from datetime import datetime

import adata

# 单价高于此阈值（元）视为高单价资产，整手不足时允许碎股建议
_HIGH_PRICE_THRESHOLD = 50.0
# 标准手数（股/手）
_LOT_SIZE = 100

from backtest.price_fetcher import fetch_prices


# ── 配置加载 ──────────────────────────────────────────────────────────────────

def load_toml(path: str) -> dict:
    with open(path, 'rb') as f:
        return tomllib.load(f)


def load_holdings(path: str) -> dict:
    """
    加载持仓配置，返回：
    { code: {name, shares, value(可选)} }
    """
    cfg = load_toml(path)
    holdings = cfg.get('holdings', {})
    if not holdings:
        raise ValueError(f"持仓配置文件 {path} 中没有 [holdings] 数据")
    return holdings, cfg.get('meta', {})


def load_strategy(path: str) -> dict:
    """
    加载策略配置，提取目标权重和 drift。
    返回：
    {
      'assets': { code: {name, weight, is_cash, ...} },
      'drift':  float,
    }
    """
    cfg = load_toml(path)
    assets = cfg.get('assets', {})
    if not assets:
        raise ValueError(f"策略配置文件 {path} 中没有 [assets] 数据")
    drift = float(cfg.get('strategy', {}).get('params', {}).get('drift', 0.05))
    return assets, drift


# ── 校验：持仓 vs 策略 ────────────────────────────────────────────────────────

def validate_consistency(holding_codes: set, strategy_codes: set, force: bool):
    """
    校验持仓与策略的资产代码是否完全一致。
    不一致时：
      - force=False → 打印差异并 sys.exit(1)
      - force=True  → 打印警告并返回需要处理的差异集合
    返回 (extra_codes, missing_codes)
      extra_codes   : 持仓有但策略没有（需卖出）
      missing_codes : 策略有但持仓没有（需买入）
    """
    extra   = holding_codes - strategy_codes   # 持仓多余
    missing = strategy_codes - holding_codes   # 持仓缺少

    if not extra and not missing:
        return set(), set()

    print('\n[!] 持仓与策略配置不匹配：')
    if extra:
        print(f'    持仓中有，策略中无（多余资产）：{", ".join(sorted(extra))}')
    if missing:
        print(f'    策略中有，持仓中无（缺少资产）：{", ".join(sorted(missing))}')

    if not force:
        print('\n    使用 --force 可强制执行：卖出多余资产，买入缺少资产')
        sys.exit(1)

    print('    --force 已启用，将卖出多余资产并买入缺少资产\n')
    return extra, missing


# ── 价格查询 ──────────────────────────────────────────────────────────────────

def resolve_market_values(holdings: dict, strategy_assets: dict, extra_codes: set) -> dict:
    """
    查询所有持仓资产（含 extra）的最新价格，计算市值。
    现金类资产（strategy 中 is_cash=True，或 extra 资产自行查询）：
      - 优先用接口查询 shares × 最新净值
      - 接口失败且配置中有 value 字段 → 使用 value，打印提示
      - 接口失败且无 value → 抛出错误
    返回：
    { code: {name, shares, price, trade_date, market_value, is_cash} }
    """
    # 需要查询价格的所有代码（持仓全部都要查）
    all_codes = list(holdings.keys())

    print('[ 查询实时价格 ]')
    prices: dict[str, tuple[float, str]] = {}
    errors: dict[str, str] = {}

    for code in all_codes:
        h = holdings[code]
        name = h.get('name', code)
        try:
            price, trade_date = _fetch_single(code)
            prices[code] = (price, trade_date)
            print(f'  {name}({code})  {price:.4f}  ({trade_date})')
        except ValueError as e:
            errors[code] = str(e)

    # 处理查询失败的情况
    failed_no_fallback = []
    for code, err_msg in errors.items():
        h = holdings[code]
        name = h.get('name', code)
        if 'value' in h:
            fallback_val = float(h['value'])
            prices[code] = (None, None)   # 特殊标记：使用 value 兜底
            print(f'  {name}({code})  [查询失败，使用配置中的 value={fallback_val:.2f}]')
        else:
            failed_no_fallback.append(f'  {name}({code})：{err_msg}')

    if failed_no_fallback:
        print('\n[错误] 以下资产价格查询失败且未配置 value 兜底：')
        for msg in failed_no_fallback:
            print(msg)
        sys.exit(1)

    # 组装结果
    result = {}
    for code in all_codes:
        h = holdings[code]
        name = h.get('name', code)
        shares = float(h.get('shares', 0))
        is_cash = strategy_assets.get(code, {}).get('is_cash', False)

        price, trade_date = prices[code]
        if price is None:
            # value 兜底
            market_value = float(h['value'])
            price_display = None
        else:
            market_value = shares * price
            price_display = price

        result[code] = {
            'name':         name,
            'shares':       shares,
            'price':        price_display,
            'trade_date':   trade_date,
            'market_value': market_value,
            'is_cash':      is_cash,
        }

    return result


def _fetch_single(code: str) -> tuple[float, str]:
    """单个代码查询，供 resolve_market_values 调用"""
    from backtest.price_fetcher import fetch_latest_price
    return fetch_latest_price(code)


def calc_lot_size(diff: float, price: float, current_shares: float) -> tuple[int, bool]:
    """
    将金额差 diff 换算为以手（100股）为单位的股数变动。

    规则：
    - 买入：向下取整到整手（100 的整数倍）
    - 卖出：向下取整到整手（100 的整数倍）
    - 高单价资产（price >= _HIGH_PRICE_THRESHOLD）且整手不足（diff 不够买/卖 1 手）：
        允许碎股建议（按实际 1 股取整），并标记 is_fractional=True

    返回 (shares_delta, is_fractional)
    shares_delta : 正=买入股数，负=卖出股数（已取整）
    is_fractional: True 表示不足整手，为碎股建议
    """
    raw_shares = abs(diff) / price  # 理论股数（未取整）
    direction  = 1 if diff > 0 else -1
    is_high_price = price >= _HIGH_PRICE_THRESHOLD

    # 尝试整手取整
    lots        = math.floor(raw_shares / _LOT_SIZE)
    lot_shares  = lots * _LOT_SIZE

    if lot_shares > 0:
        return direction * lot_shares, False

    # 不足 1 手
    if is_high_price:
        # 高单价：给出碎股建议（按 1 股取整，买入向下，卖出向下）
        frac_shares = math.floor(raw_shares)
        if frac_shares <= 0:
            frac_shares = 1 if abs(diff) >= price else 0
        if frac_shares > 0:
            return direction * frac_shares, True

    return 0, False


# ── 再平衡计算 ────────────────────────────────────────────────────────────────

def calc_rebalance(
    mv_info: dict,
    strategy_assets: dict,
    drift: float,
    extra_codes: set,
    missing_codes: set,
    min_trade: float,
) -> tuple[bool, list[dict]]:
    """
    计算是否需要再平衡，以及具体操作。

    强制情况（extra/missing 不为空）：直接触发再平衡。
    普通情况：检查任意资产偏离 > drift。

    返回 (triggered, trades)
    trades: [{code, name, action, amount, shares_delta, price, reason}]
    """
    # 总市值（仅策略内资产，extra 资产单独处理）
    strategy_codes = set(strategy_assets.keys())

    # 先将 extra 资产全部卖出，获得现金加入总池
    extra_cash = sum(mv_info[c]['market_value'] for c in extra_codes)

    # 策略内资产当前市值
    strategy_mv = {
        code: mv_info[code]['market_value']
        for code in strategy_codes
        if code in mv_info
    }
    # missing 资产市值为 0
    for code in missing_codes:
        strategy_mv[code] = 0.0

    total_value = sum(strategy_mv.values()) + extra_cash

    # 当前权重（missing 资产权重为 0）
    current_weights = {
        code: strategy_mv[code] / total_value
        for code in strategy_codes
    }
    target_weights = {
        code: float(strategy_assets[code]['weight'])
        for code in strategy_codes
    }

    # 判断是否触发
    force_trigger = bool(extra_codes or missing_codes)
    drift_violations = [
        code for code in strategy_codes
        if abs(current_weights[code] - target_weights[code]) > drift
    ]
    triggered = force_trigger or bool(drift_violations)

    if not triggered:
        return False, current_weights, target_weights, total_value, []

    # 计算每个策略资产的目标市值和差额
    trades = []

    # 1. 卖出 extra 资产（全部卖出，保守取整到整手）
    for code in sorted(extra_codes):
        info   = mv_info[code]
        amount = -info['market_value']
        price  = info['price']
        if price is not None and info['shares'] > 0:
            # 卖出全部持仓，向下取整到整手
            total_shares   = int(info['shares'])
            lot_shares     = (total_shares // _LOT_SIZE) * _LOT_SIZE
            is_high_price  = price >= _HIGH_PRICE_THRESHOLD
            if lot_shares > 0:
                shares_delta  = -lot_shares
                is_fractional = False
            elif is_high_price and total_shares > 0:
                shares_delta  = -total_shares   # 碎股建议
                is_fractional = True
            else:
                shares_delta  = -total_shares
                is_fractional = False
        else:
            shares_delta  = None
            is_fractional = False
        trades.append({
            'code':         code,
            'name':         info['name'],
            'action':       '卖出',
            'amount':       amount,
            'shares_delta': shares_delta,
            'price':        price,
            'is_fractional': is_fractional,
            'reason':       '持仓中多余资产（策略中无）',
        })

    # 2. 策略内资产买卖
    for code in strategy_codes:
        target_mv  = total_value * target_weights[code]
        current_mv = strategy_mv[code]
        diff       = target_mv - current_mv  # 正=买入，负=卖出

        if abs(diff) < min_trade:
            continue

        info    = mv_info.get(code)
        price   = info['price'] if info else None
        name    = strategy_assets[code].get('name', code)
        is_cash = strategy_assets[code].get('is_cash', False)

        if is_cash or price is None:
            shares_delta  = None
            is_fractional = False
        else:
            current_shares = info['shares'] if info else 0
            shares_delta, is_fractional = calc_lot_size(diff, price, current_shares)
            if shares_delta == 0:
                # 取整后为 0（金额不足 1 手且非高单价），跳过
                continue

        action = '买入' if diff > 0 else '卖出'
        trades.append({
            'code':          code,
            'name':          name,
            'action':        action,
            'amount':        diff,
            'shares_delta':  shares_delta,
            'price':         price,
            'is_fractional': is_fractional,
            'reason':        '缺少资产（策略中有）' if code in missing_codes else '',
        })

    # 按卖出优先排序（先卖后买，资金流转更清晰）
    trades.sort(key=lambda x: (0 if x['action'] == '卖出' else 1, x['code']))

    return triggered, current_weights, target_weights, total_value, trades


# ── 报告输出 ──────────────────────────────────────────────────────────────────

def print_report(
    port_name: str,
    mv_info: dict,
    strategy_assets: dict,
    current_weights: dict,
    target_weights: dict,
    total_value: float,
    drift: float,
    triggered: bool,
    drift_violations: list,
    trades: list[dict],
    extra_codes: set,
    missing_codes: set,
    min_trade: float,
):
    sep = '=' * 62
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f'\n{sep}')
    print(f'  {port_name} - 实时再平衡分析')
    print(f'  查询时间：{now}')
    print(sep)

    # ── 一、当前持仓状况 ──────────────────────────────────────────
    print('\n【一、当前持仓状况】')
    strategy_codes = list(strategy_assets.keys())
    # extra 资产也展示
    all_display_codes = strategy_codes + [c for c in mv_info if c not in strategy_assets]

    print(f"  {'资产':<8} {'当前价':>10} {'持仓份额':>10} {'当前市值':>14} {'当前占比':>8} {'目标占比':>8} {'偏差':>8}")
    print('  ' + '-' * 72)

    for code in all_display_codes:
        if code not in mv_info:
            # missing 资产
            name   = strategy_assets[code].get('name', code)
            target = target_weights.get(code, 0)
            cur_w  = current_weights.get(code, 0)
            drift_v = cur_w - target
            flag   = ' *** 持仓缺少' if code in missing_codes else ''
            print(f"  {name:<8} {'--':>10} {'--':>10} {'0.00':>14} {cur_w*100:>7.1f}% {target*100:>7.1f}% {drift_v*100:>+7.1f}%{flag}")
            continue

        info   = mv_info[code]
        name   = info['name']
        shares = info['shares']
        price  = info['price']
        mv     = info['market_value']
        cur_w  = current_weights.get(code, mv / total_value)
        target = target_weights.get(code, 0)
        drift_v = cur_w - target

        price_str  = f'{price:.4f}' if price is not None else '--'
        shares_str = f'{shares:,.0f}'
        flag = ''
        if code in extra_codes:
            flag = ' *** 策略中无'
        elif abs(drift_v) > drift:
            flag = ' !'

        print(f"  {name:<8} {price_str:>10} {shares_str:>10} {mv:>14,.2f} {cur_w*100:>7.1f}% {target*100:>7.1f}% {drift_v*100:>+7.1f}%{flag}")

    print('  ' + '-' * 72)
    print(f"  {'合计':<8} {'':>10} {'':>10} {total_value:>14,.2f} {'100.0%':>8}")

    # ── 二、再平衡判断 ────────────────────────────────────────────
    print(f'\n【二、再平衡判断】')
    if not triggered:
        print(f'  无需再平衡（所有资产偏差均在阈值 ±{drift*100:.1f}% 以内）')
        print(f'\n{sep}')
        return

    reasons = []
    if extra_codes:
        reasons.append(f'持仓中有策略外资产：{", ".join(sorted(extra_codes))}')
    if missing_codes:
        reasons.append(f'策略中有持仓缺少的资产：{", ".join(sorted(missing_codes))}')
    if drift_violations:
        reasons.append(f'{len(drift_violations)} 个资产偏差超过阈值 ±{drift*100:.1f}%：'
                       + ', '.join(drift_violations))
    for r in reasons:
        print(f'  需要再平衡：{r}')

    # ── 三、操作建议 ──────────────────────────────────────────────
    print(f'\n【三、操作建议】')
    if not trades:
        print(f'  所有操作金额均低于最小交易额 {min_trade:,.0f} 元，无需执行')
        print(f'\n{sep}')
        return

    print(f"  {'资产':<8} {'操作':>4} {'理论金额(元)':>14} {'手数':>6} {'股数':>8} {'实际金额(元)':>14} {'参考价':>10}  {'备注'}")
    print('  ' + '-' * 84)

    actual_cash_flow = 0.0
    has_fractional   = False
    for t in trades:
        name          = t['name']
        action        = t['action']
        amount        = t['amount']
        shares_d      = t['shares_delta']
        price         = t['price']
        reason        = t['reason']
        is_fractional = t.get('is_fractional', False)

        if is_fractional:
            has_fractional = True

        price_str  = f'{price:.4f}' if price is not None else '--'

        if shares_d is None:
            # 现金类：无手/股概念
            lots_str   = '--'
            shares_str = '(直接转账)'
            actual_amount = amount
        else:
            lots       = abs(shares_d) // _LOT_SIZE
            remainder  = abs(shares_d) % _LOT_SIZE
            direction  = '+' if shares_d > 0 else '-'

            if is_fractional:
                # 碎股：手数为0，仅显示股数，加 * 标记
                lots_str   = '0*'
                shares_str = f'{shares_d:+,d}*'
            elif remainder == 0:
                lots_str   = f'{direction}{lots:,d}手'
                shares_str = f'{shares_d:+,d}'
            else:
                # 整手 + 零头（extra 资产全卖情况）
                lots_str   = f'{direction}{lots:,d}手'
                shares_str = f'{shares_d:+,d}'

            actual_amount = shares_d * price if price is not None else amount

        actual_cash_flow += actual_amount
        actual_str = f'{actual_amount:>+14,.2f}'
        reason_str = f'[{reason}]' if reason else ''
        frac_note  = '(碎股参考)' if is_fractional else ''
        note       = ' '.join(filter(None, [reason_str, frac_note]))

        print(f"  {name:<8} {action:>4} {amount:>+14,.2f} {lots_str:>6} {shares_str:>8} {actual_str} {price_str:>10}  {note}")

    print('  ' + '-' * 84)
    rounding_diff = -actual_cash_flow
    print(f'  理论总市值：{total_value:,.2f} 元')
    if abs(rounding_diff) > 0.01:
        print(f'  取整后剩余现金误差：{rounding_diff:+,.2f} 元（可留作下次操作）')

    # ── 四、注意事项 ──────────────────────────────────────────────
    print(f'\n【四、注意事项】')
    print(f'  - 参考价为最近交易日收盘价（前复权），实际成交价可能有偏差')
    print(f'  - 整手取整：买入向下取整，卖出向下取整（1手=100股）')
    if has_fractional:
        print(f'  - 标 * 的为碎股建议（不足1手），仅供参考，实际是否可交易取决于券商规则')
    if any(strategy_assets.get(t['code'], {}).get('is_cash') for t in trades):
        print(f'  - 货币基金赎回到账可能有 T+1 延迟，请提前操作')
    if min_trade > 0:
        print(f'  - 金额低于 {min_trade:,.0f} 元的操作已忽略')

    print(f'\n{sep}')


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='持仓实时再平衡分析')
    parser.add_argument('holdings',  help='持仓配置文件，例如 config/holdings.toml')
    parser.add_argument('strategy',  help='策略配置文件，例如 config/portfolio.toml')
    parser.add_argument('--min-trade', type=float, default=1000.0,
                        metavar='N', help='最小交易金额（元），低于此金额的操作忽略，默认 1000')
    parser.add_argument('--force', action='store_true',
                        help='强制执行：卖出持仓中多余资产，买入策略中缺少资产')
    parser.add_argument('--proxy', metavar='HOST:PORT', help='HTTP 代理地址，例如 127.0.0.1:7890')
    args = parser.parse_args()

    if args.proxy:
        adata.proxy(is_proxy=True, ip=args.proxy)
        print(f'[代理] 使用 HTTP 代理：{args.proxy}')

    # ── 加载配置 ──────────────────────────────────────────────────
    holdings, holdings_meta = load_holdings(args.holdings)
    strategy_assets, drift  = load_strategy(args.strategy)

    port_name = holdings_meta.get('name', '我的投资组合')
    print(f'持仓：{port_name}')
    print(f'策略：{args.strategy}  (drift={drift*100:.1f}%)')

    # ── 校验一致性 ────────────────────────────────────────────────
    holding_codes  = set(holdings.keys())
    strategy_codes = set(strategy_assets.keys())
    extra_codes, missing_codes = validate_consistency(holding_codes, strategy_codes, args.force)

    # ── 查询价格 & 计算市值 ───────────────────────────────────────
    # missing 资产不在持仓中，无需查询
    mv_info = resolve_market_values(holdings, strategy_assets, extra_codes)

    # ── 再平衡计算 ────────────────────────────────────────────────
    triggered, current_weights, target_weights, total_value, trades = calc_rebalance(
        mv_info, strategy_assets, drift,
        extra_codes, missing_codes, args.min_trade,
    )

    # 计算偏差超阈值的资产列表（用于报告）
    drift_violations = [
        strategy_assets[c].get('name', c)
        for c in strategy_codes
        if c in current_weights and abs(current_weights[c] - target_weights.get(c, 0)) > drift
    ]

    # ── 输出报告 ──────────────────────────────────────────────────
    print_report(
        port_name, mv_info, strategy_assets,
        current_weights, target_weights, total_value,
        drift, triggered, drift_violations, trades,
        extra_codes, missing_codes, args.min_trade,
    )


if __name__ == '__main__':
    main()
