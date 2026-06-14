# AlgoTrader FastAPI Backend

## Run

From repository root:

```bash
pip install -r Algo-Trader/backend/requirements.txt
uvicorn Algo-Trader.backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /api/status`
- `GET /api/trades?limit=50`
- `POST /api/start` body:
  - `{ "mode": "paper" | "backtest", "config_path": "path-to-strategy.yaml" }`
- `POST /api/stop`

## Notes

- This backend launches the Python strategy engine via:
  - `python -m AlgoTradingNSEFO.src.app --mode live|backtest --config <yaml>`
- Trades are read from `AlgoTradingNSEFO/logs/trades.csv`.
