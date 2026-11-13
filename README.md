# Bharat Trader AI

An institutional-grade Indian stock market AI trading research, quantitative scanning, backtesting, risk management, and execution assistant built specifically for **NSE** and **BSE** in **INR (₹)**.

Inspired by [jakeschincariol/day-trader-skill](https://github.com/jakeschincariol/day-trader-skill), re-engineered from the ground up for Indian market structure, IST timings, NSE/BSE holidays, statutory Indian taxes (STT, GST, SEBI, Stamp Duty), Indian brokers (Zerodha Kite Connect, Upstox, Angel One, Dhan), and Indian financial news/regulatory feeds.

> **Disclaimer**: Bharat Trader AI is an analytical and decision-support system, not investment advice or a guaranteed-profit trading bot. Paper trading is enabled by default. Live orders require explicit user confirmation.

---

## Features & 11 Independent Modules

1. **`modules/trader-scanner/`** — Multi-timeframe (`1m`, `5m`, `15m`, `30m`, `1h`, `1d`) NSE/BSE scanner across 14 setups (ORB, VWAP breakout, EMA crossover, RSI oversold, MACD, Bollinger Squeeze, Volume breakout, Relative Strength vs NIFTY 50, 52W High, S/R breakout, Chart patterns, Gaps, Momentum, Unusual Volume).
2. **`modules/trader-news/`** — Live aggregator & classifier for RBI, SEBI, Economic Times, Moneycontrol, Business Standard, CNBC-TV18, and symbol news.
3. **`modules/trader-entry/`** — Strict completed-candle entry timing (`WAIT` / `WATCH` / `ENTRY TRIGGERED` / `SETUP INVALIDATED`). Never declares a breakout on a forming bar.
4. **`modules/trader-exit/`** — ATR + swing structure exit planner with Initial SL, Trailing SL, Target 1/2/3, and 15:15 IST intraday exit rules.
5. **`modules/trader-backtest/`** — Walk-forward backtester (look-ahead bias prevented) accounting for full Indian STT/GST/SEBI/Stamp Duty charges + 10,000-run Monte Carlo resampling.
6. **`modules/trader-risk/`** — Strict INR risk guardrails (1% risk/trade, 3% max daily loss, 1:2 min R:R, max trades/day, max open positions, sector & portfolio caps).
7. **`modules/trader-budget/`** — Cash Equity & optional F&O (disabled by default) position sizer including statutory charges.
8. **`modules/trader-broker/`** — Paper Trading Engine (default) + Zerodha Kite Connect v3, Upstox v2, Angel One SmartAPI, and DhanHQ adapters with a mandatory 7-point live approval gate.
9. **`modules/trader-alerts/`** — Dashboard & optional Telegram Bot alerts for entry, SL, target, VWAP crossover, volume spikes, and volatility surges.
10. **`modules/trader-analyst/`** — Indian Fundamental & Valuation Analyst (Revenue/EBITDA/PAT/EPS growth, ROE, ROCE, FCF, OCF, Working Capital, D/E, P/E, Forward P/E, P/B, EV/EBITDA, PEG, P/S, DCF with disclosed assumptions, Peer Comparison).
11. **`modules/trader-intelligence/`** — NIFTY 50, BANK NIFTY, FINNIFTY, India VIX, Sector Rotation, Market Breadth, USD/INR, Crude Oil, Gold, and Daily Indian Market Briefing.

---

## Installation & Setup

### 1. Environment Variables
Copy `.env.example` to `.env` and fill in optional credentials (never commit `.env`):
```bash
cp .env.example .env
```
- `GEMINI_API_KEY`: Required for server-side Gemini AI financial synthesis.
- `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN`: Optional Zerodha Kite Connect credentials.
- `UPSTOX_ACCESS_TOKEN`, `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`: Optional broker credentials.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: Optional Telegram price alert webhook.

### 2. Run the Full-Stack Web Terminal (Port 3000)
```bash
npm install
npm run dev
```
Open `http://localhost:3000`.

### 3. Run the Python CLI
Works out of the box with Python 3.10+:
```bash
python3 main.py market overview
python3 main.py scanner daily
python3 main.py scanner orb --timeframe 5m
python3 main.py scanner volume-breakout
python3 main.py analyse RELIANCE
python3 main.py analyse ORIANA
python3 main.py news --symbol HAL
python3 main.py entry RELIANCE
python3 main.py exit RELIANCE
python3 main.py backtest --symbol RELIANCE --strategy orb
python3 main.py risk check
python3 main.py budget calculate --capital 1000000 --risk 1 --entry 500 --sl 480
python3 main.py alerts check
python3 main.py portfolio
python3 main.py report daily
```

### 4. Standalone FastAPI Backend (Optional)
```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Run Automated Tests
```bash
PYTHONPATH=. bash -c 'for t in modules/*/tests/test_*.py tests/test_integration.py; do python3 "$t" || exit 1; done'
```
