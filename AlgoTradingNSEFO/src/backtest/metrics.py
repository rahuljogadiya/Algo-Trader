from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class PerformanceMetrics:
    cagr: float
    sharpe: float
    win_rate: float
    max_drawdown: float


def _sharpe_ratio(returns: np.ndarray, *, risk_free_rate_annual: float = 0.0) -> float:
    # Assumes returns are per-trade or per-period; uses sqrt(N) scaling implicitly via time index.
    if returns.size < 2:
        return 0.0
    excess = returns - (risk_free_rate_annual / 252.0)
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(returns.size))


def max_drawdown(equity_curve: np.ndarray) -> float:
    if equity_curve.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak) / peak
    return float(np.min(drawdowns))


def compute_metrics(
    *,
    initial_capital: float,
    equity_curve: Sequence[float],
    trade_pnls: Sequence[float],
) -> PerformanceMetrics:
    eq = np.asarray(equity_curve, dtype=float)
    pnls = np.asarray(trade_pnls, dtype=float)

    # Win rate
    win_rate = float(np.mean(pnls > 0)) if pnls.size else 0.0

    # Max drawdown
    mdd = max_drawdown(eq)

    # CAGR (approx) using equity start/end and assuming equity steps correspond to time periods we can't fully infer.
    # We compute CAGR using equity end growth over number of steps as "days" proxy: steps/252 years.
    if eq.size < 2 or initial_capital <= 0:
        cagr = 0.0
    else:
        total_return = (eq[-1] / initial_capital) - 1.0
        periods = max(1, eq.size - 1)
        years = periods / 252.0
        if years <= 0:
            cagr = 0.0
        else:
            cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0)

    # Sharpe from per-step returns
    if eq.size < 2:
        sharpe = 0.0
    else:
        step_returns = np.diff(eq) / eq[:-1]
        sharpe = _sharpe_ratio(step_returns)

    return PerformanceMetrics(cagr=cagr, sharpe=sharpe, win_rate=win_rate, max_drawdown=mdd)
