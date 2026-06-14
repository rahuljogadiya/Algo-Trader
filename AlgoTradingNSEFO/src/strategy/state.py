from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from AlgoTradingNSEFO.src.core.config import StrategyConfig
from AlgoTradingNSEFO.src.core.types import OptionContract


@dataclass
class PositionState:
    is_open: bool = False
    trade_id: str = ""

    underlying: str = ""
    direction: str = ""  # "CALL" | "PUT"

    contract: Optional[OptionContract] = None

    entry_time: Optional[datetime] = None
    entry_premium: float = 0.0

    stop_loss_premium: float = 0.0
    target_premium: float = 0.0
    trailing_stop_premium: float = 0.0
    # highest/lowest depending on direction; for options we use best premium
    best_premium: float = 0.0

    exit_time: Optional[datetime] = None
    exit_premium: Optional[float] = None
    exit_reason: Optional[str] = None

    # used for trailing stop progression
    last_updated_premium: float = 0.0


@dataclass
class RiskSizing:
    max_risk_amount: float
    risk_pct_capital: float


def compute_max_risk_amount(account_capital: float, cfg: StrategyConfig) -> float:
    return float(account_capital * cfg.max_risk_per_trade_pct_capital)


def initialize_new_position(
    *,
    trade_id: str,
    underlying: str,
    direction: str,
    contract: OptionContract,
    entry_time: datetime,
    entry_premium: float,
    cfg: StrategyConfig,
    account_capital: float,
) -> PositionState:
    from AlgoTradingNSEFO.src.strategy.rules import compute_risk_levels, update_trailing_stop

    risk_levels = compute_risk_levels(entry_premium, cfg=cfg)
    trailing = update_trailing_stop(entry_premium, cfg=cfg)

    max_risk_amount = compute_max_risk_amount(account_capital, cfg)

    # Note: max_risk_amount is not directly used because SL is based on premium %.
    # In a production version we can re-scale entry size vs premium SL distance.
    # Here we keep the rule strictly as given.
    _ = max_risk_amount

    st = PositionState(
        is_open=True,
        trade_id=trade_id,
        underlying=underlying,
        direction=direction,
        contract=contract,
        entry_time=entry_time,
        entry_premium=float(entry_premium),
        stop_loss_premium=risk_levels.stop_loss_premium,
        target_premium=risk_levels.target_premium,
        trailing_stop_premium=float(trailing),
        best_premium=float(entry_premium),
        last_updated_premium=float(entry_premium),
    )
    return st


def update_trailing_if_needed(state: PositionState, *, current_premium: float, cfg: StrategyConfig) -> bool:
    """
    For long options, best premium is the maximum premium achieved.
    Trailing SL is updated when we make a new best.
    """
    if not state.is_open:
        return False
    current_premium = float(current_premium)
    if current_premium > state.best_premium:
        state.best_premium = current_premium
        state.trailing_stop_premium = float(
            current_premium * (1.0 - cfg.trailing_stop_loss_pct))
        state.last_updated_premium = current_premium
        return True
    return False


def evaluate_exit(
    state: PositionState,
    *,
    current_time: datetime,
    current_premium: float,
    cfg: StrategyConfig,
) -> Optional[str]:
    """
    Returns exit_reason or None.
    Priority: target -> stop_loss -> trailing_stop.
    """
    if not state.is_open:
        return None

    p = float(current_premium)

    # target hit
    if p >= state.target_premium:
        return "target"

    # hard stop loss hit
    if p <= state.stop_loss_premium:
        return "stop_loss"

    # trailing hit
    if p <= state.trailing_stop_premium:
        return "trailing"

    return None
