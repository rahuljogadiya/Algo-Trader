from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Quote:
    symbol: str
    spot: float
    open_price: float
    last_price: float
    timestamp: datetime


@dataclass(frozen=True)
class OptionContract:
    symbol: str  # underlying symbol
    exchange: str
    instrument_token: int
    option_type: str  # "CE" or "PE"
    strike: float
    expiry: datetime


@dataclass(frozen=True)
class OptionMarketSnapshot:
    contract: OptionContract
    ltp: float
    open_interest: Optional[float]
    volume: Optional[float]
    timestamp: datetime


@dataclass(frozen=True)
class TradePlan:
    trade_id: str
    underlying: str
    direction: str  # "CALL" or "PUT"
    contract: OptionContract
    entry_premium: float
    stop_loss_premium: float
    target_premium: float
    trailing_stop_premium: float
    max_risk_amount: float
    risk_pct_capital: float


@dataclass(frozen=True)
class TradeResult:
    trade_id: str
    underlying: str
    direction: str
    contract: OptionContract
    entry_time: datetime
    exit_time: datetime
    entry_premium: float
    exit_premium: float
    pnl: float
    exit_reason: str  # "target" | "stop_loss" | "trailing" | "squareoff" | "manual" | "eod"
