from __future__ import annotations

import argparse
import sys
from pathlib import Path

from AlgoTradingNSEFO.src.core.config import load_config
from AlgoTradingNSEFO.src.core.clock import MarketClock


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="algo-trading-nsefo")
    p.add_argument("--mode", choices=["live", "backtest"], required=True)
    p.add_argument("--config", required=True, help="Path to strategy.yaml")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg_path = Path(args.config)
    app_cfg = load_config(cfg_path)

    clock = MarketClock()
    _ = clock  # for now; used by live/backtest engines

    if args.mode == "backtest":
        from AlgoTradingNSEFO.src.backtest.backtest_engine import run_backtest

        run_backtest(app_cfg)
        return 0

    if args.mode == "live":
        from AlgoTradingNSEFO.src.strategy.engine import run_live

        run_live(app_cfg)
        return 0

    raise RuntimeError(f"Unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
