from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from AlgoTradingNSEFO.src.core.clock import IST, MarketClock, parse_hhmm
from AlgoTradingNSEFO.src.core.config import AppConfig
from AlgoTradingNSEFO.src.core.types import OptionContract, OptionMarketSnapshot
from AlgoTradingNSEFO.src.strategy.rules import (
    bullish_trigger,
    bearish_trigger,
    compute_indicators,
    is_call_confirmation,
    is_put_confirmation,
)
from AlgoTradingNSEFO.src.strategy.state import (
    PositionState,
    evaluate_exit,
    update_trailing_if_needed,
    initialize_new_position,
    compute_max_risk_amount,
)
from AlgoTradingNSEFO.src.utils.csv_logger import append_trade_result
from AlgoTradingNSEFO.src.data.providers_mock import (
    fetch_top_movers_mock,
    make_intraday_ohlc_mock,
    atm_strike_rounding,
    option_contract_mock,
    make_snapshot_mock,
)


@dataclass(frozen=True)
class LiveLoopConfig:
    poll_interval_seconds: float = 1.0
    account_capital: float = 1000000.0


def _nearest_expiry_mock(now: datetime) -> datetime:
    """
    Mock nearest expiry:
    - If today is Thursday: use today
    - else use next Thursday
    """
    # weekday: Monday=0 ... Sunday=6
    days_ahead = (3 - now.weekday()) % 7  # 3 => Thursday
    if days_ahead == 0:
        return datetime(now.year, now.month, now.day, 15, 30, tzinfo=IST)
    dt = now + timedelta(days=days_ahead)
    return datetime(dt.year, dt.month, dt.day, 15, 30, tzinfo=IST)


def _select_atm_contract_mock(underlying: str, spot: float, *, option_type: str, now: datetime) -> OptionContract:
    strike = atm_strike_rounding(spot, step=50)
    expiry = _nearest_expiry_mock(now)
    return option_contract_mock(
        underlying_symbol=underlying,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        instrument_token=int(
            abs(hash((underlying, option_type, strike, expiry))) % 1000000),
    )


def _get_trade_csv_path(app_cfg: AppConfig) -> Path:
    # For now, store in ./logs/trades.csv relative to project root
    # (production: make this config-driven)
    return Path("AlgoTradingNSEFO/logs/trades.csv")


def run_live(app_cfg: AppConfig) -> None:
    """
    Live loop implementation for now runs end-to-end in mock mode.
    The full Zerodha live-ready broker wiring will be added next step.
    """
    clock = MarketClock()
    strat_cfg = app_cfg.strategy
    loop_cfg = LiveLoopConfig(account_capital=float(strat_cfg.account_capital))

    # time parsing
    avoid_first_minutes = strat_cfg.avoid_first_minutes
    no_new_trades_after = parse_hhmm(strat_cfg.no_new_trades_after_time)
    square_off_time = parse_hhmm(strat_cfg.square_off_time)

    # In this mock loop, we simulate a single decision/execution cycle across symbols.
    now = clock.now()

    # Avoid first N minutes after open
    if clock.today_open_dt(ref=now) > now + timedelta(minutes=1):
        raise RuntimeError("Market not open yet in mock live loop.")

    if clock.is_within_first_minutes(avoid_first_minutes, ref=now):
        # In real engine, just skip entries.
        print("Skipping entries: within first 15 minutes after market open (mock).")
        return

    if clock.cutoff_time_reached(no_new_trades_after, ref=now):
        print("Skipping entries: after no-new-trades cutoff (mock).")
        return

    # Fetch top movers (mock)
    universe = [f"STK{i}" for i in range(1, 51)]
    top = fetch_top_movers_mock(
        limit=strat_cfg.top_gainers_losers_limit,
        symbols_universe=universe,
        seed=42,
        ts=now,
    )

    # Only one position at a time in this simplified engine
    position: Optional[PositionState] = None

    trade_log_path = _get_trade_csv_path(app_cfg)
    trade_log_path.parent.mkdir(parents=True, exist_ok=True)

    def try_entry(mover: tuple[str, float, float, float, str]) -> Optional[PositionState]:
        nonlocal position
        if position is not None and position.is_open:
            return None

        underlying, spot_open, spot_last, spot_last_for_strike, direction = mover

        option_type = "CALL" if direction == "CALL" else "PUT"
        contract = _select_atm_contract_mock(
            underlying, spot_last_for_strike, option_type=option_type, now=now)

        # Mock option snapshot
        snap = make_snapshot_mock(
            contract=contract,
            underlying_open=spot_open,
            underlying_last=spot_last_for_strike,
            ts=now,
        )

        if snap.volume is None or snap.open_interest is None:
            return None
        if snap.volume < strat_cfg.min_option_volume:
            return None
        if snap.open_interest < strat_cfg.min_option_open_interest:
            return None

        # EMA/RSI confirmation from intraday OHLC
        ohlc = make_intraday_ohlc_mock(
            spot_open=spot_open, ts_end=now, minutes=120, start_minutes_ago=120)
        ind = compute_indicators(ohlc, cfg=strat_cfg)

        if option_type == "CALL":
            if not is_call_confirmation(ind, cfg=strat_cfg):
                return None
        else:
            if not is_put_confirmation(ind, cfg=strat_cfg):
                return None

        trade_id = str(uuid.uuid4())
        st = initialize_new_position(
            trade_id=trade_id,
            underlying=underlying,
            direction=option_type,
            contract=contract,
            entry_time=now,
            entry_premium=snap.ltp,
            cfg=strat_cfg,
            account_capital=loop_cfg.account_capital,
        )
        return st

    # Decide candidate entries
    # For each mover: +2% from open => CALL; -2% => PUT
    candidates: list[tuple[str, float, float, float, str]] = []
    for m in top:
        underlying = m.symbol
        spot_open = m.spot_open
        spot_last = m.spot_last
        if bullish_trigger(spot_open, spot_last, cfg=strat_cfg):
            candidates.append((underlying, float(spot_open), float(
                spot_last), float(spot_last), "CALL"))
        elif bearish_trigger(spot_open, spot_last, cfg=strat_cfg):
            candidates.append((underlying, float(spot_open),
                              float(spot_last), float(spot_last), "PUT"))

    # Pick first valid candidate (simplified)
    for c in candidates:
        position = try_entry(c)
        if position is not None:
            break

    if position is None or not position.is_open:
        print("No trades placed in mock live loop.")
        return

    # Simulate monitoring for few steps until square-off
    # In real engine, this would poll LTP from Kite.
    end_time = datetime(now.year, now.month, now.day,
                        square_off_time.hour, square_off_time.minute, tzinfo=IST)
    t = now
    step = timedelta(minutes=2)
    best_seen = position.best_premium

    while t <= end_time and position.is_open:
        # update option premium with a crude random walk based on time
        # (we reuse snapshot model with small shifts by using underlying_last approximations)
        # just to feed into premium model shape
        underlying_last_proxy = position.entry_premium
        # We'll directly evolve premium using a deterministic function of time for repeatability
        elapsed_min = max(0, int((t - now).total_seconds() // 60))
        premium = position.entry_premium * \
            (1 + 0.01 * (elapsed_min / 2))  # trending up
        # Add slight oscillation
        premium = premium * (1 + (1 if elapsed_min % 6 < 3 else -1) * 0.003)

        updated = update_trailing_if_needed(
            position, current_premium=premium, cfg=strat_cfg)
        best_seen = position.best_premium if updated else best_seen

        reason = evaluate_exit(position, current_time=t,
                               current_premium=premium, cfg=strat_cfg)
        if reason is not None:
            position.is_open = False
            position.exit_time = t
            position.exit_premium = float(premium)
            position.exit_reason = reason
            break

        t += step

    # If still open at square-off
    if position.is_open:
        position.is_open = False
        position.exit_time = end_time
        # mock: close at trailing or entry premium scaled
        position.exit_premium = float(position.best_premium * 0.98)
        position.exit_reason = "squareoff"

    if position.exit_time is None or position.exit_premium is None:
        raise RuntimeError("Position exited without exit info (mock).")

    pnl = position.exit_premium - position.entry_premium

    from AlgoTradingNSEFO.src.core.types import TradeResult

    result = TradeResult(
        trade_id=position.trade_id,
        underlying=position.underlying,
        direction="CALL" if position.direction == "CALL" else "PUT",
        contract=position.contract,  # type: ignore[arg-type]
        entry_time=position.entry_time,  # type: ignore[arg-type]
        exit_time=position.exit_time,
        entry_premium=position.entry_premium,
        exit_premium=position.exit_premium,
        pnl=pnl,
        exit_reason=position.exit_reason or "manual",
    )

    append_trade_result(trade_log_path, result, timestamp=now)
    print(
        f"Mock trade executed. TradeId={result.trade_id} P&L={result.pnl} Reason={result.exit_reason}")
