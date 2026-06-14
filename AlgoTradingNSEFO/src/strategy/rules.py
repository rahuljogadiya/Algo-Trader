from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from AlgoTradingNSEFO.src.core.config import StrategyConfig


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    # Wilder's RSI
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / length, adjust=False,
                        min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False,
                        min_periods=length).mean()

    rs = avg_gain / (avg_loss.replace(0.0, np.nan))
    out = 100 - (100 / (1 + rs))
    return out.fillna(0.0)


@dataclass(frozen=True)
class Indicators:
    ema_fast: float
    ema_slow: float
    rsi: float


def compute_indicators(df: pd.DataFrame, *, cfg: StrategyConfig, close_col: str = "close") -> Indicators:
    if close_col not in df.columns:
        raise KeyError(f"Missing column '{close_col}' in OHLCV dataframe")

    closes = df[close_col].astype(float)
    ema_fast_s = ema(closes, cfg.ema_fast)
    ema_slow_s = ema(closes, cfg.ema_slow)
    rsi_s = rsi(closes, cfg.rsi_length)

    if df.empty:
        raise ValueError("Cannot compute indicators on empty dataframe")

    return Indicators(
        ema_fast=float(ema_fast_s.iloc[-1]),
        ema_slow=float(ema_slow_s.iloc[-1]),
        rsi=float(rsi_s.iloc[-1]),
    )


def is_call_confirmation(ind: Indicators, *, cfg: StrategyConfig) -> bool:
    return ind.ema_fast > ind.ema_slow and ind.rsi > cfg.rsi_call_threshold


def is_put_confirmation(ind: Indicators, *, cfg: StrategyConfig) -> bool:
    return ind.ema_fast < ind.ema_slow and ind.rsi < cfg.rsi_put_threshold


def bullish_trigger(spot_open: float, spot_last: float, *, cfg: StrategyConfig) -> bool:
    if spot_open <= 0:
        return False
    pct = (spot_last - spot_open) / spot_open
    return pct >= cfg.move_pct_from_open


def bearish_trigger(spot_open: float, spot_last: float, *, cfg: StrategyConfig) -> bool:
    if spot_open <= 0:
        return False
    pct = (spot_last - spot_open) / spot_open
    return pct <= -cfg.move_pct_from_open


@dataclass(frozen=True)
class RiskLevels:
    stop_loss_premium: float
    target_premium: float
    trailing_stop_premium: float


def compute_risk_levels(entry_premium: float, *, cfg: StrategyConfig) -> RiskLevels:
    sl = entry_premium * (1.0 - cfg.stop_loss_pct_premium_loss)
    tgt = entry_premium * (1.0 + cfg.target_pct_premium_gain)
    trailing = entry_premium * (1.0 - cfg.trailing_stop_loss_pct)
    return RiskLevels(
        stop_loss_premium=float(sl),
        target_premium=float(tgt),
        trailing_stop_premium=float(trailing),
    )


def update_trailing_stop(best_premium: float, *, cfg: StrategyConfig) -> float:
    # trailing stop = best * (1 - trailing_pct)
    return float(best_premium * (1.0 - cfg.trailing_stop_loss_pct))
