from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from AlgoTradingNSEFO.src.core.types import Quote, OptionContract, OptionMarketSnapshot


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class TopMover:
    symbol: str
    direction: str  # "gainer" | "loser"
    spot_open: float
    spot_last: float
    timestamp: datetime


def _mock_quote(symbol: str, spot_open: float, spot_last: float, ts: datetime) -> Quote:
    return Quote(
        symbol=symbol,
        spot=float(spot_last),
        open_price=float(spot_open),
        last_price=float(spot_last),
        timestamp=ts,
    )


def fetch_top_movers_mock(
    *,
    limit: int,
    symbols_universe: list[str],
    seed: int = 1,
    ts: datetime,
) -> list[TopMover]:
    rng = random.Random(seed)
    out: list[TopMover] = []
    candidates = symbols_universe[:]
    rng.shuffle(candidates)
    for sym in candidates[:limit]:
        spot_open = rng.randint(100, 3000)
        # make half gainers, half losers
        if rng.random() > 0.5:
            move = 1.02 + rng.random() * 0.05  # +2% to +7%
            direction = "gainer"
        else:
            move = 0.98 - rng.random() * 0.05  # -2% to -7%
            direction = "loser"

        spot_last = round(spot_open * move, 2)
        out.append(
            TopMover(
                symbol=sym,
                direction=direction,
                spot_open=float(spot_open),
                spot_last=float(spot_last),
                timestamp=ts,
            )
        )
    return out


def option_contract_mock(
    *,
    underlying_symbol: str,
    option_type: str,
    strike: float,
    expiry: datetime,
    instrument_token: int = 0,
) -> OptionContract:
    return OptionContract(
        symbol=underlying_symbol,
        exchange="NFO",
        instrument_token=int(instrument_token),
        option_type=option_type,
        strike=float(strike),
        expiry=expiry,
    )


def atm_strike_rounding(spot: float, step: int = 50) -> float:
    return float(int(round(spot / step)) * step)


def make_snapshot_mock(
    *,
    contract: OptionContract,
    underlying_open: float,
    underlying_last: float,
    ts: datetime,
) -> OptionMarketSnapshot:
    # crude premium model:
    # intrinsic proxy = |underlying_last - strike|
    intrinsic = abs(underlying_last - contract.strike)
    base = 50.0 + intrinsic * 0.02
    # directional bias for CE/PE
    if contract.option_type == "CE":
        bias = 1.10 if underlying_last >= underlying_open else 0.90
    else:
        bias = 1.10 if underlying_last <= underlying_open else 0.90

    premium = base * bias
    vol = float(10000 + rng_int_hash(contract.strike, ts) %
                5000)  # deterministic-ish
    oi = float(5000 + rng_int_hash(contract.strike * 2, ts) % 5000)

    return OptionMarketSnapshot(
        contract=contract,
        ltp=float(round(premium, 2)),
        open_interest=oi,
        volume=vol,
        timestamp=ts,
    )


def rng_int_hash(a: float, ts: datetime) -> int:
    # deterministic-ish small hash
    x = int(abs(a) * 1000) + ts.timetuple().tm_yday * \
        1000 + ts.hour * 60 + ts.minute
    return x % 100000


def make_intraday_ohlc_mock(
    *,
    spot_open: float,
    ts_end: datetime,
    minutes: int = 60,
    start_minutes_ago: int = 60,
    step_minutes: int = 1,
) -> pd.DataFrame:
    rng = np.random.default_rng(int(ts_end.timestamp()) % (2**32 - 1))
    times = [ts_end - timedelta(minutes=start_minutes_ago - i)
             for i in range(0, minutes, step_minutes)]
    prices = [spot_open]
    for _ in range(len(times) - 1):
        prices.append(prices[-1] * (1 + rng.normal(0, 0.002)))
    prices = np.array(prices, dtype=float)
    o = prices
    c = prices * (1 + rng.normal(0, 0.0015, size=len(prices)))
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.001)))
    l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.001)))

    df = pd.DataFrame(
        {
            "timestamp": times,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        }
    )
    return df
