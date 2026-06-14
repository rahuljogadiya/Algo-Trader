import pandas as pd

from AlgoTradingNSEFO.src.core.config import StrategyConfig
from AlgoTradingNSEFO.src.strategy import rules


def test_triggers_plus_minus_2pct_from_open():
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

    # +2% => bullish
    assert rules.bullish_trigger(100.0, 102.0, cfg=cfg) is True
    assert rules.bullish_trigger(100.0, 101.99, cfg=cfg) is False

    # -2% => bearish
    assert rules.bearish_trigger(100.0, 98.0, cfg=cfg) is True
    assert rules.bearish_trigger(100.0, 98.01, cfg=cfg) is False


def test_confirmation_logic_call_put():
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

    ind = rules.Indicators(ema_fast=10, ema_slow=5, rsi=61)
    assert rules.is_call_confirmation(ind, cfg=cfg) is True
    assert rules.is_put_confirmation(ind, cfg=cfg) is False

    ind2 = rules.Indicators(ema_fast=4, ema_slow=8, rsi=39)
    assert rules.is_put_confirmation(ind2, cfg=cfg) is True
    assert rules.is_call_confirmation(ind2, cfg=cfg) is False


def test_compute_indicators_requires_close():
    df = pd.DataFrame({"x": [1, 2, 3]})
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
    try:
        rules.compute_indicators(df, cfg=cfg, close_col="close")
        assert False, "Expected KeyError"
    except KeyError:
        assert True
