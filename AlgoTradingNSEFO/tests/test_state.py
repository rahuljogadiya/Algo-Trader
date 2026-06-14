from datetime import datetime

from AlgoTradingNSEFO.src.core.config import StrategyConfig
from AlgoTradingNSEFO.src.strategy.state import (
    evaluate_exit,
    initialize_new_position,
    update_trailing_if_needed,
)


def test_initialize_new_position_sets_levels_and_trailing():
    cfg = StrategyConfig(
        ema_fast=20,
        ema_slow=50,
        rsi_length=14,
        rsi_call_threshold=60,
        rsi_put_threshold=40,
        move_pct_from_open=0.02,
        stop_loss_pct_premium_loss=0.2,
        target_pct_premium_gain=0.4,
        trailing_stop_loss_pct=0.1,
        avoid_first_minutes=15,
        no_new_trades_after_time="14:45",
        square_off_time="15:20",
        min_option_volume=1,
        min_option_open_interest=1,
        max_risk_per_trade_pct_capital=0.01,
    )

    # OptionContract minimal fields for PositionState
    from AlgoTradingNSEFO.src.core.types import OptionContract

    contract = OptionContract(
        symbol="RELIANCE",
        exchange="NFO",
        instrument_token=0,
        option_type="CE",
        strike=1050,
        expiry=datetime(2026, 6, 18, 15, 30),
    )

    entry = 100.0
    st = initialize_new_position(
        trade_id="t1",
        underlying="RELIANCE",
        direction="CALL",
        contract=contract,
        entry_time=datetime(2026, 6, 14, 10, 0),
        entry_premium=entry,
        cfg=cfg,
        account_capital=1_000_000.0,
    )

    assert st.stop_loss_premium == entry * (1 - cfg.stop_loss_pct_premium_loss)
    assert st.target_premium == entry * (1 + cfg.target_pct_premium_gain)
    assert st.trailing_stop_premium == entry * (1 - cfg.trailing_stop_loss_pct)


def test_update_trailing_only_when_best_improves():
    cfg = StrategyConfig(
        ema_fast=20,
        ema_slow=50,
        rsi_length=14,
        rsi_call_threshold=60,
        rsi_put_threshold=40,
        move_pct_from_open=0.02,
        stop_loss_pct_premium_loss=0.2,
        target_pct_premium_gain=0.4,
        trailing_stop_loss_pct=0.1,
        avoid_first_minutes=15,
        no_new_trades_after_time="14:45",
        square_off_time="15:20",
        min_option_volume=1,
        min_option_open_interest=1,
        max_risk_per_trade_pct_capital=0.01,
    )

    from AlgoTradingNSEFO.src.core.types import OptionContract

    contract = OptionContract(
        symbol="RELIANCE",
        exchange="NFO",
        instrument_token=0,
        option_type="CE",
        strike=1050,
        expiry=datetime(2026, 6, 18, 15, 30),
    )

    st = initialize_new_position(
        trade_id="t1",
        underlying="RELIANCE",
        direction="CALL",
        contract=contract,
        entry_time=datetime(2026, 6, 14, 10, 0),
        entry_premium=100.0,
        cfg=cfg,
        account_capital=1_000_000.0,
    )

    # lower premium shouldn't update trailing
    updated = update_trailing_if_needed(st, current_premium=99.0, cfg=cfg)
    assert updated is False
    trailing_before = st.trailing_stop_premium

    updated2 = update_trailing_if_needed(st, current_premium=120.0, cfg=cfg)
    assert updated2 is True
    assert st.trailing_stop_premium == 120.0 * (1 - cfg.trailing_stop_loss_pct)
    assert st.trailing_stop_premium != trailing_before


def test_evaluate_exit_priority_target_stop_trailing():
    cfg = StrategyConfig(
        ema_fast=20,
        ema_slow=50,
        rsi_length=14,
        rsi_call_threshold=60,
        rsi_put_threshold=40,
        move_pct_from_open=0.02,
        stop_loss_pct_premium_loss=0.2,
        target_pct_premium_gain=0.4,
        trailing_stop_loss_pct=0.1,
        avoid_first_minutes=15,
        no_new_trades_after_time="14:45",
        square_off_time="15:20",
        min_option_volume=1,
        min_option_open_interest=1,
        max_risk_per_trade_pct_capital=0.01,
    )

    from AlgoTradingNSEFO.src.core.types import OptionContract

    contract = OptionContract(
        symbol="RELIANCE",
        exchange="NFO",
        instrument_token=0,
        option_type="CE",
        strike=1050,
        expiry=datetime(2026, 6, 18, 15, 30),
    )

    st = initialize_new_position(
        trade_id="t1",
        underlying="RELIANCE",
        direction="CALL",
        contract=contract,
        entry_time=datetime(2026, 6, 14, 10, 0),
        entry_premium=100.0,
        cfg=cfg,
        account_capital=1_000_000.0,
    )

    ts = datetime(2026, 6, 14, 11, 0)
    # target takes precedence
    assert evaluate_exit(st, current_time=ts,
                         current_premium=150.0, cfg=cfg) == "target"

    # stop loss
    st.trailing_stop_premium = 50.0  # ensure trailing won't be hit first
    assert evaluate_exit(st, current_time=ts,
                         current_premium=80.0, cfg=cfg) == "stop_loss"

    # trailing
    st.stop_loss_premium = 10.0  # ensure stop won't be hit first
    st.trailing_stop_premium = 95.0
    assert evaluate_exit(st, current_time=ts,
                         current_premium=94.0, cfg=cfg) == "trailing"
