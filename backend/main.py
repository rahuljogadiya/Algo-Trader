from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


APP_ROOT = Path(__file__).resolve().parents[1]  # Algo-Trader/
REPO_ROOT = APP_ROOT.parent  # workspace root containing AlgoTradingNSEFO/

TRADES_CSV = REPO_ROOT / "AlgoTradingNSEFO" / "logs" / "trades.csv"

DEFAULT_STRATEGY_CONFIG = REPO_ROOT / \
    "AlgoTradingNSEFO" / "config" / "strategy.yaml"


class RunMode(str):
    PAPER = "paper"
    BACKTEST = "backtest"


@dataclass
class RunState:
    lock: threading.Lock
    process: Optional[subprocess.Popen[bytes]]
    mode: Optional[str]
    started_at: Optional[datetime]
    last_error: Optional[str]

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process = None
        self.mode = None
        self.started_at = None
        self.last_error = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


run_state = RunState()
app = FastAPI(title="AlgoTrader Backend", version="0.1.0")

# Enable local dev CORS for PWA/localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRequest(BaseModel):
    mode: str
    config_path: Optional[str] = None
    # Optional: number of seconds for backtest (current engine runs based on data; kept for future)
    extra: Optional[dict[str, Any]] = None


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    with run_state.lock:
        return {
            "running": run_state.is_running(),
            "mode": run_state.mode,
            "startedAt": run_state.started_at.isoformat() if run_state.started_at else None,
            "lastError": run_state.last_error,
        }


def _read_trades_csv(limit: int = 50) -> list[dict[str, Any]]:
    if not TRADES_CSV.exists() or TRADES_CSV.stat().st_size == 0:
        return []

    rows: list[dict[str, Any]] = []
    with TRADES_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            rows.append(r)
            if i + 1 >= limit:
                break
    return rows


@app.get("/api/trades")
def api_trades(limit: int = 50) -> list[dict[str, Any]]:
    return _read_trades_csv(limit=limit)


def _spawn_algo_process(mode: str, config_path: Path) -> subprocess.Popen[bytes]:
    """
    Runs AlgoTradingNSEFO's CLI entry via `python -m AlgoTradingNSEFO.src.app`.
    Paper trading is currently implemented as `--mode live` (mock/paper loop).
    """
    python_exe = os.environ.get("PYTHON", None)
    if python_exe:
        cmd = [python_exe]
    else:
        cmd = ["python"]

    if mode == RunMode.PAPER:
        # The AlgoTradingNSEFO app uses --mode live as its paper-trading loop currently.
        app_mode = "live"
    elif mode == RunMode.BACKTEST:
        app_mode = "backtest"
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    cmd += [
        "-m",
        "AlgoTradingNSEFO.src.app",
        "--mode",
        app_mode,
        "--config",
        str(config_path),
    ]

    # Ensure cwd is repo root so module resolution works reliably
    return subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _stream_process_output(proc: subprocess.Popen[bytes]) -> None:
    """
    Non-blocking output collector to avoid pipe deadlock.
    """
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, b""):
        if not line:
            break
    try:
        proc.stdout.close()
    except Exception:
        pass


def _run(mode: str, config_path: Path) -> None:
    with run_state.lock:
        if run_state.is_running():
            raise RuntimeError("A run is already in progress.")
        run_state.mode = mode
        run_state.started_at = datetime.now()
        run_state.last_error = None

        # Reset last_error and keep running state consistent
        proc = _spawn_algo_process(mode, config_path)
        run_state.process = proc

    # Stream in background to prevent blocking
    t = threading.Thread(target=_stream_process_output,
                         args=(proc,), daemon=True)
    t.start()

    # Wait for completion
    rc = proc.wait()
    with run_state.lock:
        # Mark stopped
        if rc != 0:
            run_state.last_error = f"Process exited with code {rc}"
        run_state.process = None
        run_state.mode = mode if run_state.last_error is None else None


@app.post("/api/start")
def api_start(req: StartRequest) -> dict[str, Any]:
    mode = req.mode.strip().lower()

    if mode not in (RunMode.PAPER, RunMode.BACKTEST):
        raise HTTPException(
            status_code=400, detail="mode must be 'paper' or 'backtest'")

    config_path = Path(
        req.config_path) if req.config_path else DEFAULT_STRATEGY_CONFIG
    if not config_path.exists():
        raise HTTPException(
            status_code=400, detail=f"Config file not found: {config_path}")

    try:
        th = threading.Thread(target=_run, args=(
            mode, config_path), daemon=True)
        th.start()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "mode": mode}


@app.post("/api/stop")
def api_stop() -> dict[str, Any]:
    with run_state.lock:
        proc = run_state.process
        if proc is None:
            return {"ok": True, "stopped": False, "reason": "No running process"}

        try:
            proc.send_signal(signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        run_state.last_error = None

    # Give it a moment
    time.sleep(0.3)
    return {"ok": True, "stopped": True}
