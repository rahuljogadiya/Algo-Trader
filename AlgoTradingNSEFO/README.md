# algo-trading-nsefo

Automated NSE F&O intraday strategy (Top Gainers/Losers → ATM Options) with:

- Live trading (Zerodha Kite Connect) using live-ready placeholders
- Backtesting module (CSV-driven historical replay)
- Config-driven rules, OOP modular architecture, retry + error handling
- CSV trade logging

## Quick start (backtest)

1. Edit config: `AlgoTradingNSEFO/config/strategy.yaml`
2. Run:

```bash
python -m AlgoTradingNSEFO.src.app --mode backtest --config AlgoTradingNSEFO/config/strategy.yaml
```

## Quick start (live-ready code)

Set credentials in the YAML under `broker`:

- `api_key`
- `access_token`

Then run:

```bash
python -m AlgoTradingNSEFO.src.app --mode live --config AlgoTradingNSEFO/config/strategy.yaml
```

## Project layout

- `AlgoTradingNSEFO/src/` contains strategy, data providers, broker integration, backtest engine, utilities.
