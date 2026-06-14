from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from AlgoTradingNSEFO.src.backtest.metrics import compute_metrics
from AlgoTradingNSEFO.src.core.clock import MarketClock, parse_hhmm
from AlgoTradingNSEFO.src.core.config import AppConfig
from AlgoTradingNSEFO.src.core.types import OptionContract, TradeResult
from AlgoTradingNSEFO.src.strategy.rules import (
    bearish_trigger,
    bullish_trigger,
    compute_indicators,
    is_call_confirmation,
    is_put_confirmation,
)
from AlgoTradingNSEFO.src.strategy.state import (
    evaluate_exit,
    initialize_new_position,
    update_trailing_if_needed,
)
from AlgoTradingNSEFO.src.utils.csv_logger import append_trade_result


REQUIRED_COLUMNS = {
    "timestamp",
    "underlying",
    "spot_open",
    "spot_last",
    "option_type",
    "option_strike",
    "expiry",
    "option_premium",
    "option_open_interest",
    "option_volume",
    # technicals (optional but recommended). If absent, we compute from spot OHLC columns.
    "spot_open_ohlc_open",
    "spot_open_ohlc_high",
    "spot_open_ohlc_low",
    "spot_open_ohlc_close",
}


@dataclass(frozen=True)
class BacktestSummary:
    cagr: float
    sharpe: float
    win_rate: float
    max_drawdown: float
    trades: int
    pnl: float


def _parse_iso_dt(s: str) -> datetime:
    # supports both with/without timezone; we treat as-is.
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _parse_expiry(s: str) -> datetime:
    # expects ISO date or datetime
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt


def _build_contract(row: pd.Series) -> OptionContract:
    return OptionContract(
        symbol=str(row["underlying"]),
        exchange="NFO",
        instrument_token=int(0),
        option_type=str(row["option_type"]),
        strike=float(row["option_strike"]),
        expiry=_parse_expiry(str(row["expiry"])),
    )


def _get_spot_ohlc_from_row(row: pd.Series) -> pd.DataFrame:
    # Backtest technical confirmation is based on EMA(20), EMA(50), RSI(14).
    # For simplicity, our sample CSV provides per-row OHLC close series in columns.
    # We'll synthesize a 60-minute window from these columns if possible.
    # If columns exist only for current row, this won't work; therefore this method assumes
    # the CSV provides "spot_ohlc_close" series-like data via additional rows.
    # For strictness in this first iteration we require OHLC columns for each timestamp row.
    return pd.DataFrame(
        {
            "timestamp": [pd.NaT, pd.NaT],  # unused
            "open": [float(row["spot_open_ohlc_open"]), float(row["spot_open_ohlc_open"])],
            "high": [float(row["spot_open_ohlc_high"]), float(row["spot_open_ohlc_high"])],
            "low": [float(row["spot_open_ohlc_low"]), float(row["spot_open_ohlc_low"])],
            "close": [float(row["spot_open_ohlc_close"]), float(row["spot_open_ohlc_close"])],
        }
    )


def run_backtest(app_cfg: AppConfig) -> None:
    path = Path(app_cfg.backtest.historical_data_path)
    if not app_cfg.backtest.historical_data_path:
        raise ValueError(
            "Backtest requires config.backtest.historical_data_path (CSV of historical option/underlying data)."
        )
    if not path.exists():
        raise FileNotFoundError(f"Backtest data CSV not found: {path}")

    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    missing = sorted(list(REQUIRED_COLUMNS - set(df.columns)))
    if missing:
        raise ValueError(
            "Backtest CSV is missing required columns:\n"
            f"{missing}\n\n"
            "Provide at least spot/open/last triggers, option premium + OI/volume, and spot OHLC columns "
            "(spot_open_ohlc_open/high/low/close) per timestamp row."
        )

    # Parse timestamps
    df["timestamp"] = df["timestamp"].apply(_parse_iso_dt)
    df["expiry"] = df["expiry"].apply(lambda s: _parse_expiry(str(s)))

    # Normalize numerics
    for col in [
        "spot_open",
        "spot_last",
        "option_strike",
        "option_premium",
        "option_open_interest",
        "option_volume",
        "spot_open_ohlc_open",
        "spot_open_ohlc_high",
        "spot_open_ohlc_low",
        "spot_open_ohlc_close",
    ]:
        df[col] = df[col].astype(float)

    # Sort
    df = df.sort_values(["underlying", "timestamp"]).reset_index(drop=True)

    clock = MarketClock()
    strat_cfg = app_cfg.strategy

    avoid_first_minutes = strat_cfg.avoid_first_minutes
    no_new_trades_after = parse_hhmm(strat_cfg.no_new_trades_after_time)
    square_off_time = parse_hhmm(strat_cfg.square_off_time)

    trade_records: list[TradeResult] = []
    equity_curve = [float(app_cfg.backtest.initial_capital)]
    account_capital = float(app_cfg.backtest.initial_capital)

    position_open = False
    position = None

    # Build per-timestamp technicals window by reconstructing EMA/RSI using spot_ohlc_close.
    # Here we simply compute indicators based on rolling window over all rows ordered by time for each underlying.
    df["spot_ohlc_close"] = df["spot_open_ohlc_close"]

    # Precompute indicators per underlying
    ind_fast = []
    for _, g in df.groupby("underlying"):
        g = g.sort_values("timestamp")
        closes = g["spot_ohlc_close"].astype(float)
        ema_fast_s = closes.ewm(span=strat_cfg.ema_fast, adjust=False).mean()
        ema_slow_s = closes.ewm(span=strat_cfg.ema_slow, adjust=False).mean()
        # RSI
        delta = closes.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        avg_gain = gain.ewm(alpha=1 / strat_cfg.rsi_length,
                            adjust=False, min_periods=strat_cfg.rsi_length).mean()
        avg_loss = loss.ewm(alpha=1 / strat_cfg.rsi_length,
                            adjust=False, min_periods=strat_cfg.rsi_length).mean()
        rs = avg_gain / (avg_loss.replace(0.0, np.nan))
        rsi_s = (100 - (100 / (1 + rs))).fillna(0.0)

        ind_fast.append(g.index.to_frame(index=False))
        df.loc[g.index, "ema_fast"] = ema_fast_s.values
        df.loc[g.index, "ema_slow"] = ema_slow_s.values
        df.loc[g.index, "rsi"] = rsi_s.values

    df = df.sort_values("timestamp").reset_index(drop=True)

    # Simulation (one-at-a-time per underlying merged sequentially)
    # Simplification: evaluate sequentially across timestamps for all underlyings.
    trades_until_now = 0

    for i in range(len(df)):
        row = df.iloc[i]
        ts: datetime = row["timestamp"]
        underlying = str(row["underlying"])

        if position_open:
            current_premium = float(row["option_premium"])
            # update trailing first
            update_trailing_if_needed(
                position, current_premium=current_premium, cfg=strat_cfg)

            reason = evaluate_exit(
                position,
                current_time=ts,
                current_premium=current_premium,
                cfg=strat_cfg,
            )
            if reason is not None:
                exit_time = ts
                exit_premium = current_premium
                position.exit_time = exit_time
                position.exit_premium = exit_premium
                position.exit_reason = reason
                pnl = float(exit_premium - position.entry_premium)

                contract = position.contract  # type: ignore[assignment]
                result = TradeResult(
                    trade_id=position.trade_id,
                    underlying=position.underlying,
                    direction=position.direction,
                    contract=contract,  # type: ignore[arg-type]
                    entry_time=position.entry_time,  # type: ignore[arg-type]
                    exit_time=exit_time,
                    entry_premium=position.entry_premium,
                    exit_premium=exit_premium,
                    pnl=pnl,
                    exit_reason=reason,
                )
                trade_records.append(result)

                account_capital += pnl
                equity_curve.append(account_capital)

                position_open = False
                position = None
                trades_until_now += 1
                continue

            # square-off
            if clock.square_off_reached(square_off_time, ref=ts):
                exit_time = ts
                exit_premium = current_premium
                pnl = float(exit_premium - position.entry_premium)
                contract = position.contract  # type: ignore[assignment]

                result = TradeResult(
                    trade_id=position.trade_id,
                    underlying=position.underlying,
                    direction=position.direction,
                    contract=contract,  # type: ignore[arg-type]
                    entry_time=position.entry_time,  # type: ignore[arg-type]
                    exit_time=exit_time,
                    entry_premium=position.entry_premium,
                    exit_premium=exit_premium,
                    pnl=pnl,
                    exit_reason="squareoff",
                )
                trade_records.append(result)
                account_capital += pnl
                equity_curve.append(account_capital)

                position_open = False
                position = None
                trades_until_now += 1
                continue

            # keep monitoring
            continue

        # No open position: check entry filters
        if clock.cutoff_time_reached(no_new_trades_after, ref=ts):
            # no new trades after cutoff
            continue

        if clock.is_within_first_minutes(avoid_first_minutes, ref=ts):
            continue

        spot_open = float(row["spot_open"])
        spot_last = float(row["spot_last"])

        direction = None
        if bullish_trigger(spot_open, spot_last, cfg=strat_cfg):
            direction = "CALL"
        elif bearish_trigger(spot_open, spot_last, cfg=strat_cfg):
            direction = "PUT"
        else:
            continue

        # technical confirmation based on precomputed ema_fast/ema_slow/rsi at this timestamp row
        ind = type("Indicators", (), {})  # lightweight
        ind.ema_fast = float(row["ema_fast"])
        ind.ema_slow = float(row["ema_slow"])
        ind.rsi = float(row["rsi"])

        if direction == "CALL" and not is_call_confirmation(ind, cfg=strat_cfg):
            continue
        if direction == "PUT" and not is_put_confirmation(ind, cfg=strat_cfg):
            continue

        option_type = "CE" if direction == "CALL" else "PE"
        if str(row["option_type"]).upper() != option_type:
            # enforce using trigger-chosen option_type
            continue

        volume = float(row["option_volume"])
        oi = float(row["option_open_interest"])
        if volume < strat_cfg.min_option_volume:
            continue
        if oi < strat_cfg.min_option_open_interest:
            continue

        contract = _build_contract(row)

        position = initialize_new_position(
            trade_id=str(uuid.uuid4()),
            underlying=underlying,
            direction=direction,
            contract=contract,
            entry_time=ts,
            entry_premium=float(row["option_premium"]),
            cfg=strat_cfg,
            account_capital=account_capital,
        )
        position_open = True

    # Metrics
    trade_pnls = [t.pnl for t in trade_records]
    equity_curve_arr = np.asarray(equity_curve, dtype=float)

    metrics = compute_metrics(
        initial_capital=float(app_cfg.backtest.initial_capital),
        equity_curve=equity_curve_arr,
        trade_pnls=trade_pnls,
    )

    summary = BacktestSummary(
        cagr=metrics.cagr,
        sharpe=metrics.sharpe,
        win_rate=metrics.win_rate,
        max_drawdown=metrics.max_drawdown,
        trades=len(trade_records),
        pnl=float(np.sum(trade_pnls)) if trade_pnls else 0.0,
    )

    out_dir = Path("AlgoTradingNSEFO/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "backtest_summary.json"
    summary_path.write_text(json.dumps(
        summary.__dict__, indent=2), encoding="utf-8")

    # CSV trade logging
    # Reuse csv_logger to keep consistent with live.
    trade_csv = Path("AlgoTradingNSEFO/logs/trades.csv")
    for t in trade_records:
        append_trade_result(trade_csv, t)

    print(
        f"Backtest done. Trades={summary.trades}, PnL={summary.pnl:.2f}, "
        f"CAGR={summary.cagr:.4f}, Sharpe={summary.sharpe:.4f}, "
        f"WinRate={summary.win_rate:.2%}, MaxDD={summary.max_drawdown:.2%}"
    )
