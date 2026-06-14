from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class StrategyConfig:
    # Capital / sizing
    account_capital: float = 1000000.0

    # Trade selection
    top_gainers_losers_limit: int = 10
    min_option_volume: float = 1000.0
    min_option_open_interest: float = 1000.0

    # Entry triggers
    move_pct_from_open: float = 0.02  # +2% / -2% vs day open

    # Technical confirmation
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_length: int = 14
    rsi_call_threshold: float = 60.0
    rsi_put_threshold: float = 40.0

    # Risk management
    stop_loss_pct_premium_loss: float = 0.20  # 20% premium loss
    target_pct_premium_gain: float = 0.40     # 40% premium gain
    trailing_stop_loss_pct: float = 0.10     # 10% trailing based on best premium
    max_risk_per_trade_pct_capital: float = 0.01  # 1% of account capital

    # Time filters (IST)
    avoid_first_minutes: int = 15
    no_new_trades_after_time: str = "14:45"
    square_off_time: str = "15:20"


@dataclass(frozen=True)
class BrokerConfig:
    mode: str = "mock"  # "live-ready" or "mock"
    api_key: str = ""
    access_token: str = ""
    # For Zerodha:
    # account_capital is not directly from broker; we use config for sizing
    order_variety: str = "regular"


@dataclass(frozen=True)
class BacktestConfig:
    historical_data_path: str = ""  # CSV path to options+underlying bars
    initial_capital: float = 1000000.0
    # if CSV provides direction+premiums; otherwise strategy sim uses derived columns
    tz: str = "Asia/Kolkata"


@dataclass(frozen=True)
class AppConfig:
    strategy: StrategyConfig
    broker: BrokerConfig
    backtest: BacktestConfig


def _load_raw(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if path.suffix.lower() in (".yml", ".yaml"):
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported config extension: {path.suffix}")


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    raw = _load_raw(p)

    strat_raw = raw.get("strategy", {}) if isinstance(raw, Mapping) else {}
    broker_raw = raw.get("broker", {}) if isinstance(raw, Mapping) else {}
    back_raw = raw.get("backtest", {}) if isinstance(raw, Mapping) else {}

    # --- Secrets handling for public repos ---
    # If broker.api_key / broker.access_token are blank in YAML,
    # allow local environment variables to provide them.
    import os

    api_key = broker_raw.get("api_key", "") if isinstance(
        broker_raw, Mapping) else ""
    access_token = broker_raw.get("access_token", "") if isinstance(
        broker_raw, Mapping) else ""

    if not api_key:
        api_key = os.getenv("Zerodha_API_KEY", "") or ""
    if not access_token:
        access_token = os.getenv("Zerodha_ACCESS_TOKEN", "") or ""

    # Broker mode: allow overriding via env, or default to existing YAML value.
    # If mode isn't provided in YAML but secrets are present, switch to live-ready.
    broker_mode = broker_raw.get("mode", "mock") if isinstance(
        broker_raw, Mapping) else "mock"
    if broker_mode == "mock" and api_key and access_token:
        broker_mode = "live-ready"

    broker_payload = dict(broker_raw) if isinstance(
        broker_raw, Mapping) else {}
    broker_payload["api_key"] = api_key
    broker_payload["access_token"] = access_token
    broker_payload["mode"] = broker_mode

    strategy = StrategyConfig(**strat_raw)
    broker = BrokerConfig(**broker_payload)
    backtest = BacktestConfig(**back_raw)

    return AppConfig(strategy=strategy, broker=broker, backtest=backtest)
