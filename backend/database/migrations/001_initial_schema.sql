-- Bharat Trader AI — PostgreSQL Schema Migration (001_initial_schema.sql)
-- Compatible with Supabase PostgreSQL 15+ and Render Managed PostgreSQL.

CREATE TABLE IF NOT EXISTS stocks_master (
    stock_id TEXT PRIMARY KEY,
    isin TEXT,
    nse_symbol TEXT,
    bse_code TEXT,
    yahoo_symbol TEXT,
    company_name TEXT NOT NULL,
    series TEXT DEFAULT 'EQ',
    sector TEXT DEFAULT 'Indian Equities',
    industry TEXT DEFAULT 'Diversified',
    exchange TEXT DEFAULT 'NSE',
    market_cap_cr DOUBLE PRECISION,
    cap_tier TEXT,
    trading_status TEXT DEFAULT 'ACTIVE',
    screener_url TEXT,
    aliases_json TEXT DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stocks_nse ON stocks_master(nse_symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_bse ON stocks_master(bse_code);
CREATE INDEX IF NOT EXISTS idx_stocks_isin ON stocks_master(isin);
CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks_master(company_name);

CREATE TABLE IF NOT EXISTS screener_company_data (
    id SERIAL PRIMARY KEY,
    stock_id TEXT NOT NULL,
    company_name TEXT,
    nse_symbol TEXT,
    bse_code TEXT,
    isin TEXT,
    screener_url TEXT,
    source TEXT NOT NULL,
    statement_scope TEXT DEFAULT 'Unspecified',
    reporting_period TEXT,
    is_estimated INTEGER DEFAULT 0,
    ratios_json TEXT DEFAULT '{}',
    pnl_annual_json TEXT DEFAULT '[]',
    quarters_json TEXT DEFAULT '[]',
    balance_sheet_json TEXT DEFAULT '[]',
    cash_flow_json TEXT DEFAULT '[]',
    shareholding_json TEXT DEFAULT '[]',
    business_notes_json TEXT DEFAULT '{}',
    peers_json TEXT DEFAULT '[]',
    missing_fields_json TEXT DEFAULT '[]',
    imported_at TEXT NOT NULL,
    UNIQUE(stock_id, source, statement_scope)
);

CREATE TABLE IF NOT EXISTS screener_screens (
    screen_id TEXT PRIMARY KEY,
    screen_name TEXT NOT NULL,
    source_filename TEXT,
    columns_json TEXT DEFAULT '[]',
    rows_json TEXT DEFAULT '[]',
    row_count INTEGER DEFAULT 0,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_price_cache (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    last_price DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    volume BIGINT,
    source TEXT,
    last_bar_ist TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_fundamental_analyses (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    business_quality_score DOUBLE PRECISION,
    financial_strength_score DOUBLE PRECISION,
    growth_score DOUBLE PRECISION,
    valuation_score DOUBLE PRECISION,
    overall_assessment TEXT,
    analysis_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_trading_analyses (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    entry_status TEXT,
    risk_verdict TEXT,
    workflow_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_signals (
    signal_id TEXT PRIMARY KEY,
    stock_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    strategy TEXT NOT NULL,
    signal_direction TEXT,
    score DOUBLE PRECISION,
    price DOUBLE PRECISION,
    reasons_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlists (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    sector TEXT DEFAULT 'Indian Equities',
    added_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange)
);

CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_id TEXT PRIMARY KEY,
    stock_id TEXT,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    initial_capital DOUBLE PRECISION,
    final_capital DOUBLE PRECISION,
    net_pnl DOUBLE PRECISION,
    win_rate_pct DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown_pct DOUBLE PRECISION,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION,
    target DOUBLE PRECISION,
    status TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'paper',
    charges_inr DOUBLE PRECISION DEFAULT 0.0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    product TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_price DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION,
    target DOUBLE PRECISION,
    sector TEXT,
    opened_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange, product)
);

CREATE TABLE IF NOT EXISTS trade_journal (
    trade_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    strategy TEXT,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    gross_pnl DOUBLE PRECISION NOT NULL,
    charges_inr DOUBLE PRECISION NOT NULL,
    net_pnl DOUBLE PRECISION NOT NULL,
    mode TEXT NOT NULL DEFAULT 'paper',
    opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS price_alerts (
    alert_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    telegram_notify INTEGER DEFAULT 0,
    last_triggered_at TEXT,
    created_at TEXT NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS kv_store (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
