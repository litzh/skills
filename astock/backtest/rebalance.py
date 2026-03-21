# -*- coding: utf-8 -*-
"""
再平衡策略模块
定义策略基类和四种具体实现，通过 make_strategy() 工厂函数按配置实例化。

策略类型：
  threshold_and_periodic  — 阈值触发 + 定期触发（并集）
  threshold_only          — 仅阈值触发
  periodic_only           — 仅定期触发
  buy_and_hold            — 永不触发（用于基准对比）
"""

import pandas as pd


class RebalanceStrategy:
    """再平衡策略基类"""

    def prepare(self, trade_dates: list[str]):
        """预计算阶段（如生成定期触发日集合），在回测开始前调用一次"""
        pass

    def should_rebalance(
        self,
        date: str,
        weights: dict[str, float],
        target_weights: dict[str, float],
        is_first_day: bool,
    ) -> tuple[bool, str]:
        """
        判断当日是否触发再平衡。
        返回 (triggered: bool, reason: str)
        第一个交易日（建仓日）永远不触发。

        weights        : 当前各资产实际权重
        target_weights : 各资产目标权重（来自配置）
        """
        raise NotImplementedError


class BuyAndHold(RebalanceStrategy):
    """永不再平衡"""

    def should_rebalance(self, date, weights, target_weights, is_first_day):
        return False, ''


class ThresholdOnly(RebalanceStrategy):
    """
    仅阈值触发（相对偏差）
    任意资产实际权重偏离目标权重超过 ±drift 即触发。
    例：drift=0.05，目标 20% → 触发区间 [15%, 25%]
                    目标 60% → 触发区间 [55%, 65%]
    """

    def __init__(self, drift: float):
        self.drift = drift

    def should_rebalance(self, date, weights, target_weights, is_first_day):
        if is_first_day:
            return False, ''
        triggered = any(
            abs(weights[code] - target_weights[code]) > self.drift
            for code in weights
        )
        return (triggered, '阈值触发') if triggered else (False, '')


class PeriodicOnly(RebalanceStrategy):
    """仅定期触发（指定月份的最后一个交易日）"""

    def __init__(self, periodic_months: list[int]):
        self.periodic_months = set(periodic_months)
        self._periodic_dates: set[str] = set()

    def prepare(self, trade_dates: list[str]):
        df = pd.DataFrame({'trade_date': trade_dates})
        df['ym'] = df['trade_date'].str[:7]
        for ym, group in df.groupby('ym'):
            month = int(ym[5:7])
            if month in self.periodic_months:
                self._periodic_dates.add(group['trade_date'].iloc[-1])

    def should_rebalance(self, date, weights, target_weights, is_first_day):
        if is_first_day:
            return False, ''
        if date in self._periodic_dates:
            return True, '定期再平衡'
        return False, ''


class ThresholdAndPeriodic(RebalanceStrategy):
    """阈值触发 + 定期触发（并集，同一天只触发一次）"""

    def __init__(self, drift: float, periodic_months: list[int]):
        self._threshold = ThresholdOnly(drift)
        self._periodic  = PeriodicOnly(periodic_months)

    def prepare(self, trade_dates: list[str]):
        self._periodic.prepare(trade_dates)

    def should_rebalance(self, date, weights, target_weights, is_first_day):
        if is_first_day:
            return False, ''
        triggered, reason = self._threshold.should_rebalance(date, weights, target_weights, is_first_day)
        if triggered:
            return True, reason
        return self._periodic.should_rebalance(date, weights, target_weights, is_first_day)


# ── 工厂函数 ────────────────────────────────────────────────────────────────

def make_strategy(strategy_cfg: dict) -> RebalanceStrategy:
    """
    根据配置字典创建策略实例。
    strategy_cfg 对应 TOML 中的 [strategy] 段：
      { 'type': '...', 'params': { 'drift': ..., 'periodic_months': [...] } }
    """
    stype  = strategy_cfg.get('type', 'threshold_and_periodic')
    params = strategy_cfg.get('params', {})

    drift           = float(params.get('drift', 0.05))
    periodic_months = list(params.get('periodic_months', [6, 12]))

    if stype == 'buy_and_hold':
        return BuyAndHold()
    elif stype == 'threshold_only':
        return ThresholdOnly(drift)
    elif stype == 'periodic_only':
        return PeriodicOnly(periodic_months)
    elif stype == 'threshold_and_periodic':
        return ThresholdAndPeriodic(drift, periodic_months)
    else:
        raise ValueError(f"未知策略类型：{stype}，可选：threshold_and_periodic / threshold_only / periodic_only / buy_and_hold")
