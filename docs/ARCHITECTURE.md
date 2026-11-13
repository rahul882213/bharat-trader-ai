# Bharat Trader AI — System Architecture

## 1. Layered Design
1. **Data Provider Layer (`backend/data_providers/`)**:
   - Interchangeable `MarketDataProvider` adapters.
   - `nse_master.py`: Official NSE `EQUITY_L.csv` master list (~2,000+ active equities) + curated index constituent registries (NIFTY 50, Next 50, 100, 200, 500, Bank Nifty, FinNifty, Midcap 150, Smallcap 250, Sectoral Indices).
   - `yahoo_provider.py`: Unofficial Yahoo Finance v8 Chart & v10 QuoteSummary with cookie/crumb auth, throttling, stale bar detection, and mandatory `Yahoo Finance (Unofficial)` attribution.
   - `provider_manager.py`: Routes requests across authorized broker APIs (when configured) and supplementary providers without single-vendor lock-in.

2. **Core Quantitative Services (`backend/services/`)**:
   - `market_calendar.py`: IST (`Asia/Kolkata`) market session state machine (`PRE_OPEN 09:00-09:15`, `REGULAR_OPEN 09:15-15:30`, `15:15 MIS square-off`, NSE/BSE holiday calendar, special Muhurat/Budget sessions).
   - `indicators.py`: SMA, EMA (9/21/50/200), Wilder RSI(14), MACD(12,26,9), Bollinger Bands(20,2), ATR(14), Session-Anchored VWAP, Swing Highs/Lows, Floor Pivots, Candlestick Patterns.
   - `indian_charges.py`: Exact Indian statutory & discount broker cost model (Brokerage, STT, NSE/BSE Exchange Txn, SEBI ₹10/Cr, Stamp Duty, 18% GST).
   - `workflow.py`: 12-Step connected research pipeline exchanging structured JSON via `trader/*.json`.

3. **11 Independent Trading Modules (`modules/trader-*`)**:
   - Each module is self-contained with `SKILL.md`, `README.md`, `config.example.json`, Python engine, and unit tests.

4. **Broker Adapters (`backend/broker_adapters/`)**:
   - `PaperBrokerAdapter` (enabled by default, SQLite + `trader/orders.json` + `trader/trade_history.json`).
   - `ZerodhaKiteAdapter` (Kite Connect v3 REST API + SHA-256 session checksum).
   - `UpstoxAdapter`, `AngelOneAdapter`, `DhanAdapter`.
   - 7-item explicit user confirmation gate prior to any live broker order dispatch.

5. **Web Terminal & AI Layer (`server.ts` + `src/`)**:
   - Express server on port 3000 bridging React UI to the Python quantitative engine + server-side `@google/genai` (`gemini-4-hydrogen`) structured research synthesis.
   - Frontend built with React, TypeScript, Tailwind CSS, TradingView Lightweight Charts, and Recharts.
