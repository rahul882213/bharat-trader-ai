# Bharat Trader AI

An institutional-grade Indian stock market AI trading research, quantitative scanning, Screener.in fundamental integration, walk-forward backtesting, risk management, and execution platform built specifically for **NSE** and **BSE** in **INR (₹)**.

> **Disclaimer**: Bharat Trader AI is an analytical and decision-support platform, not investment advice. Paper trading is enabled by default. Live broker orders require explicit approval and backend credentials. No market prices or financial numbers are ever fabricated when feeds or database records are unavailable.

---

## Architecture Overview

- **Frontend (GitHub Pages / Vite React + TypeScript):** Deployed at `https://rahul882213.github.io/bharat-trader-ai/`, communicating over **HTTPS** with the FastAPI backend via `VITE_API_BASE_URL` (with live `/health` status monitoring, DB connectivity display, provider status, and last-update tracking).
- **Backend (Production FastAPI on Render):** `backend/main.py` & `backend/api/routes.py` serving Universal NSE/BSE Stock Master Search, Screener.in CSV/XLSX imports, Dynamic 12-Step AI Analysis (`run_analysis`), Market-Wide Scanning, Historical Backtesting (with STT/GST/SEBI/Stamp Duty + 10,000 Monte Carlo), Risk Management, Trade Journal, Paper Trading, Alerts, and Server-Side Gemini AI synthesis.
- **Database (Supabase PostgreSQL / SQLite):** Managed via `backend/database/db.py` and `backend/database/migrations/001_initial_schema.sql`. Stores `stocks_master`, `screener_company_data`, `screener_screens`, `market_price_cache`, `ai_fundamental_analyses`, `ai_trading_analyses`, `technical_signals`, `watchlists`, `backtest_results`, `paper_orders`, `paper_positions`, `trade_journal`, `price_alerts`, and `kv_store`.

---

## Core Modules (`modules/`)

1. **`modules/trader-scanner/`** — Mode 1 Technical Setups + Mode 2 Market-Wide Multi-Factor NSE/BSE Scanner.
2. **`modules/trader-screener/`** — Screener.in CSV & `.xlsx` importer, symbol/ISIN deduplication, Screener URL linking, missing-field audit, and optional throttled public adapter.
3. **`modules/trader-analyst/`** — Indian Fundamental & Valuation Analyst fusing Screener.in DB imports + Yahoo Finance into 4 evidenced scores (`Business Quality`, `Financial Strength`, `Growth`, `Valuation`).
4. **`modules/trader-news/`** — RBI, SEBI, Economic Times, Moneycontrol, Business Standard, CNBC-TV18, and company news aggregator.
5. **`modules/trader-entry/`** — Completed-candle entry timing (`WAIT` / `WATCH` / `ENTRY TRIGGERED` / `SETUP INVALIDATED`).
6. **`modules/trader-exit/`** — ATR + swing exit planner with Initial SL, Trailing SL, Target 1/2/3, and 15:15 IST intraday closeout rules.
7. **`modules/trader-backtest/`** — Walk-forward backtester (no look-ahead bias) with Indian charges + 10,000-run Monte Carlo resampling and DB history persistence.
8. **`modules/trader-risk/`** — INR risk guardrails (max risk/trade, daily drawdown limit, min R:R, sector/portfolio caps).
9. **`modules/trader-budget/`** — Position sizer accounting for statutory Indian taxes and charges.
10. **`modules/trader-broker/`** — Paper Trading Engine + Zerodha Kite Connect, Upstox, Angel One, DhanHQ adapters.
11. **`modules/trader-alerts/`** — Price/indicator/news alerts + optional Telegram notifications.
12. **`modules/trader-intelligence/`** — NIFTY 50, BANK NIFTY, FINNIFTY, India VIX, Sector Rotation, Macro, and Daily Market Briefing.

---

## Cloud Deployment Guide: Supabase PostgreSQL + Render FastAPI + GitHub Pages

### Step 1: Create PostgreSQL Database on Supabase
1. Sign in to [Supabase](https://supabase.com/) and create a new project (e.g., `bharat-trader-db`, region **Mumbai / ap-south-1** or **Singapore**).
2. Open **Project Settings -> Database -> Connection string -> URI** (select **Transaction Pooler** or **Session Pooler** URI so IPv4/Render connections work reliably).
3. Copy the URI and append `?sslmode=require`, e.g.:
   `postgresql://postgres.<project-ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require`
4. *(Optional Manual SQL Migration)* Open **Supabase -> SQL Editor**, paste the contents of `backend/database/migrations/001_initial_schema.sql`, and click **Run** (this also runs automatically during the Render build/startup script).

### Step 2: Deploy FastAPI Backend on Render
1. Sign in to [Render](https://render.com/) and click **New -> Blueprint** (or **New -> Web Service**) connected to `rahul882213/bharat-trader-ai`.
2. Render automatically detects `render.yaml`:
   - **Build Command:** `pip install -r requirements.txt && python3 -m backend.database.init_db_script`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. In Render **Environment Variables**, set:
   - `DATABASE_URL` = your Supabase PostgreSQL connection URI (`?sslmode=require`)
   - `GEMINI_API_KEY` = your Google Gemini API key (kept strictly server-side)
   - `ALLOWED_ORIGINS` = `https://rahul882213.github.io`
   - `TRADING_MODE` = `paper`
4. Deploy and wait for Render to pass `/health`. Verify by opening `https://<your-render-service>.onrender.com/health` in your browser — you should see `"status": "ok"`, `"database": { "connected": true, "dialect": "postgresql" }`, and `"stock_master_count": 2636`.

### Step 3: Connect the Live GitHub Pages Frontend
Option A — **Rebuild & Deploy `gh-pages` with `VITE_API_BASE_URL` baked in:**
```bash
VITE_API_BASE_URL=https://<your-render-service>.onrender.com VITE_BASE_PATH=/bharat-trader-ai/ npm run build
```
Push `dist/` to `gh-pages` (or set `VITE_API_BASE_URL` in your CI build environment).

Option B — **Connect Instantly Without Rebuilding:**
1. Open `https://rahul882213.github.io/bharat-trader-ai/`.
2. Click **Configure HTTPS API** in the top health status bar.
3. Paste your live Render HTTPS URL (`https://<your-render-service>.onrender.com`) and click **Connect HTTPS Backend**.
4. The status bar immediately verifies `GET /health` and displays **Backend: Connected**, **DB: Connected (postgresql)**, **Providers**, and **Last Update**.

---

## Automated Verification & Tests

Run all Python module & integration test suites:
```bash
PYTHONPATH=. bash -c 'for t in modules/*/tests/test_*.py tests/test_integration.py; do python3 "$t" || exit 1; done'
```

Initialize or re-sync database tables + 2,636 NSE/BSE equities manually:
```bash
python3 -m backend.database.init_db_script
```
