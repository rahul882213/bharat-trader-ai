"""Bharat Trader AI — Central Universal Database Layer (PostgreSQL + SQLite)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "bharat_trader.db"

_INIT_LOCK = threading.Lock()
_INITIALIZED_URLS: set[str] = set()


def get_database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def is_postgres() -> bool:
    url = get_database_url().lower()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def get_db_dialect() -> str:
    return "postgresql" if is_postgres() else "sqlite"


def _normalize_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _to_pg_sql(sql: str) -> str:
    """Convert SQLite '?' positional placeholders to PostgreSQL '%s' outside string literals."""
    out: List[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            in_single = not in_single
        elif ch == "?" and not in_single:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _sqlite_path() -> Path:
    db_url = get_database_url()
    path = DB_PATH
    if db_url.startswith("sqlite:///"):
        raw = db_url.replace("sqlite:///", "", 1)
        path = Path(raw) if Path(raw).is_absolute() else (ROOT_DIR / raw)
    return path


def get_connection():
    if is_postgres():
        import psycopg2
        import psycopg2.extras

        pg_url = _normalize_pg_url(get_database_url())
        return psycopg2.connect(pg_url, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=10)
    conn = sqlite3.connect(str(_sqlite_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_COMMON_TABLES = """
-- 1. Central Universal Stock Master Table (ISIN as preferred identity)
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
    market_cap_cr REAL,
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

-- 2. Screener.in & Authorized Fundamental Imports (Linked by stock_id / ISIN)
CREATE TABLE IF NOT EXISTS screener_company_data (
    id {SERIAL_PK},
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
    ratios_json TEXT DEFAULT '{{}}',
    pnl_annual_json TEXT DEFAULT '[]',
    quarters_json TEXT DEFAULT '[]',
    balance_sheet_json TEXT DEFAULT '[]',
    cash_flow_json TEXT DEFAULT '[]',
    shareholding_json TEXT DEFAULT '[]',
    business_notes_json TEXT DEFAULT '{{}}',
    peers_json TEXT DEFAULT '[]',
    missing_fields_json TEXT DEFAULT '[]',
    imported_at TEXT NOT NULL,
    UNIQUE(stock_id, source, statement_scope)
);

-- 3. Screener.in Exported Stock Screens
CREATE TABLE IF NOT EXISTS screener_screens (
    screen_id TEXT PRIMARY KEY,
    screen_name TEXT NOT NULL,
    source_filename TEXT,
    columns_json TEXT DEFAULT '[]',
    rows_json TEXT DEFAULT '[]',
    row_count INTEGER DEFAULT 0,
    imported_at TEXT NOT NULL
);

-- 4. Market Price Cache (Linked by stock_id)
CREATE TABLE IF NOT EXISTS market_price_cache (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    last_price REAL,
    change_pct REAL,
    volume BIGINT,
    source TEXT,
    last_bar_ist TEXT,
    fetched_at TEXT NOT NULL
);

-- 5. AI Fundamental Analyses (Linked by stock_id)
CREATE TABLE IF NOT EXISTS ai_fundamental_analyses (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    business_quality_score REAL,
    financial_strength_score REAL,
    growth_score REAL,
    valuation_score REAL,
    overall_assessment TEXT,
    analysis_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 6. AI Trading Workflow Analyses (Linked by stock_id)
CREATE TABLE IF NOT EXISTS ai_trading_analyses (
    stock_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    entry_status TEXT,
    risk_verdict TEXT,
    workflow_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 7. Technical Signals History (Scanner & Workflow signals)
CREATE TABLE IF NOT EXISTS technical_signals (
    signal_id TEXT PRIMARY KEY,
    stock_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    strategy TEXT NOT NULL,
    signal_direction TEXT,
    score REAL,
    price REAL,
    reasons_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

-- 8. Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    sector TEXT DEFAULT 'Indian Equities',
    added_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange)
);

-- 9. Backtest Results History
CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_id TEXT PRIMARY KEY,
    stock_id TEXT,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    initial_capital REAL,
    final_capital REAL,
    net_pnl REAL,
    win_rate_pct REAL,
    sharpe_ratio REAL,
    max_drawdown_pct REAL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 10. Paper Trading Orders, Positions, Trade Journal & Alerts
CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    stop_loss REAL,
    target REAL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'paper',
    charges_inr REAL DEFAULT 0.0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    product TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_price REAL NOT NULL,
    stop_loss REAL,
    target REAL,
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
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    gross_pnl REAL NOT NULL,
    charges_inr REAL NOT NULL,
    net_pnl REAL NOT NULL,
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
    threshold REAL,
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
"""


def get_schema_sql(dialect: str) -> str:
    serial_pk = "SERIAL PRIMARY KEY" if dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return _COMMON_TABLES.format(SERIAL_PK=serial_pk)


def init_db(force: bool = False) -> None:
    cache_key = get_database_url() or str(_sqlite_path())
    if not force and cache_key in _INITIALIZED_URLS:
        return
    with _INIT_LOCK:
        if not force and cache_key in _INITIALIZED_URLS:
            return
        dialect = get_db_dialect()
        ddl = get_schema_sql(dialect)
        conn = get_connection()
        try:
            if dialect == "postgresql":
                cur = conn.cursor()
                for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
                    cur.execute(stmt)
                conn.commit()
                cur.close()
            else:
                conn.executescript(ddl)
                conn.commit()
            _INITIALIZED_URLS.add(cache_key)
        finally:
            conn.close()


def query_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    init_db()
    conn = get_connection()
    try:
        if is_postgres():
            cur = conn.cursor()
            cur.execute(_to_pg_sql(sql), params)
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def execute_sql(sql: str, params: tuple = ()) -> None:
    init_db()
    conn = get_connection()
    try:
        if is_postgres():
            cur = conn.cursor()
            cur.execute(_to_pg_sql(sql), params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()
    finally:
        conn.close()


def execute_many(sql: str, rows: List[tuple]) -> None:
    if not rows:
        return
    init_db()
    conn = get_connection()
    try:
        if is_postgres():
            import psycopg2.extras

            cur = conn.cursor()
            pg_sql = _to_pg_sql(sql)
            psycopg2.extras.execute_batch(cur, pg_sql, rows, page_size=250)
            conn.commit()
            cur.close()
        else:
            conn.executemany(sql, rows)
            conn.commit()
    finally:
        conn.close()


def get_kv(key: str) -> Optional[Any]:
    rows = query_all("SELECT v FROM kv_store WHERE k = ?", (key,))
    if not rows:
        return None
    try:
        return json.loads(rows[0]["v"])
    except Exception:
        return rows[0]["v"]


def set_kv(key: str, value: Any, updated_at: str) -> None:
    execute_sql(
        """
        INSERT INTO kv_store (k, v, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(k) DO UPDATE SET
            v = excluded.v,
            updated_at = excluded.updated_at
        """,
        (key, json.dumps(value), updated_at),
    )


def check_db_health() -> Dict[str, Any]:
    dialect = get_db_dialect()
    try:
        init_db()
        rows = query_all("SELECT COUNT(*) AS c FROM stocks_master")
        stock_cnt = int(rows[0]["c"]) if rows else 0
        latest_cache = query_all("SELECT MAX(fetched_at) AS ts FROM market_price_cache")
        last_price_ts = latest_cache[0]["ts"] if latest_cache else None
        last_sync_ts = get_kv("stocks_master_synced_at")
        last_update = max([x for x in [last_price_ts, last_sync_ts] if x], default=None)
        return {
            "connected": True,
            "dialect": dialect,
            "stock_master_count": stock_cnt,
            "last_data_update": last_update,
            "error": None,
        }
    except Exception as exc:
        return {
            "connected": False,
            "dialect": dialect,
            "stock_master_count": 0,
            "last_data_update": None,
            "error": str(exc),
        }
