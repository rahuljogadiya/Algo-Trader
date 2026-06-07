# AlgoTrader 📈

A fully automated algorithmic trading system for Indian F&O markets (NSE).
Built with Python + FastAPI backend and a PWA mobile dashboard installable on iPhone.

## Strategy
- Scans all F&O stocks at 9:30 AM daily
- Identifies top gainers (bullish market) and top losers (bearish market)
- Buys ATM CE/PE on current week expiry
- Auto exit on 10% SL or ₹2500 target

## Features
- Live F&O market scanner (NSE data)
- Paper trading engine — no real money needed
- Trade logging with entry/exit reasons, P&L
- PWA dashboard — installable on iPhone, no App Store needed
- FastAPI backend with start/stop controls

## Tech Stack
- Python, FastAPI, SQLite
- NSE API + Upstox API
- HTML/CSS/JS PWA (no framework)

## Status
🚧 Under development — paper trading phase
