from __future__ import annotations

from datetime import datetime
from pathlib import Path

from AlgoTradingNSEFO.src.core.types import OptionContract, TradeResult
from AlgoTradingNSEFO.src.utils.csv_logger import append_trade_result


def test_append_trade_result_creates_header_and_appends(tmp_path: Path):
    out = tmp_path / "trades.csv"

    contract = OptionContract(
        symbol="RELIANCE",
        exchange="NFO",
        instrument_token=0,
        option_type="CE",
        strike=1050,
        expiry=datetime(2026, 6, 18, 15, 30),
    )

    result = TradeResult(
        trade_id="t-1",
        underlying="RELIANCE",
        direction="CALL",
        contract=contract,
        entry_time=datetime(2026, 6, 14, 10, 0),
        exit_time=datetime(2026, 6, 14, 10, 30),
        entry_premium=100.0,
        exit_premium=140.0,
        pnl=40.0,
        exit_reason="target",
    )

    append_trade_result(out, result, timestamp=datetime(2026, 6, 14, 10, 0))

    text = out.read_text(encoding="utf-8").splitlines()
    assert len(text) >= 2  # header + 1 row

    header = text[0].split(",")
    assert "trade_id" in header
    assert "option_symbol" in header
    assert "pnl" in header
