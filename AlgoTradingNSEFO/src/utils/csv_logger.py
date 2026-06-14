from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from AlgoTradingNSEFO.src.core.types import TradeResult


TRADE_CSV_COLUMNS = [
    "timestamp",
    "trade_id",
    "underlying",
    "direction",
    "option_symbol",
    "option_type",
    "strike",
    "expiry",
    "entry_time",
    "exit_time",
    "entry_premium",
    "exit_premium",
    "pnl",
    "exit_reason",
]


def _ensure_header(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_CSV_COLUMNS)
        writer.writeheader()


def append_trade_result(path: str | Path, result: TradeResult, *, timestamp: datetime | None = None) -> None:
    out = Path(path)
    _ensure_header(out)

    row = {
        "timestamp": (timestamp or datetime.now()).isoformat(),
        "trade_id": result.trade_id,
        "underlying": result.underlying,
        "direction": result.direction,
        "option_symbol": result.contract.symbol,
        "option_type": result.contract.option_type,
        "strike": result.contract.strike,
        "expiry": result.contract.expiry.isoformat(),
        "entry_time": result.entry_time.isoformat(),
        "exit_time": result.exit_time.isoformat(),
        "entry_premium": result.entry_premium,
        "exit_premium": result.exit_premium,
        "pnl": result.pnl,
        "exit_reason": result.exit_reason,
    }

    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_CSV_COLUMNS)
        writer.writerow(row)


def append_many_trade_results(path: str | Path, results: Iterable[TradeResult]) -> None:
    for r in results:
        append_trade_result(path, r)
