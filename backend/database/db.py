"""Bharat Trader AI — Central Universal Database Layer (SQLite default, PostgreSQL ready)."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "bharat_trader.db"


def get_connection() -> sqlite3.Connection:
    db_url = os.getenv("DATABASE_URL", "")
    path = DB_PATH
    if db_url.startswith("sqlite:///"):
        raw = db_url.replace("sqlite:///", "", 1)
        path = Path(raw) if Path(raw).is_absolute() else (ROOT_DIR / raw)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            volume INTEGER,
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

        -- 7. Paper Trading Orders, Positions, Journal & Alerts
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
    )
    conn.commit()
    conn.close()


def query_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    init_db()
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute_sql(sql: str, params: tuple = ()) -> None:
    init_db()
    conn = get_connection()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def execute_many(sql: str, rows: List[tuple]) -> None:
    init_db()
    conn = get_connection()
    conn.executemany(sql, rows)
    conn.commit()
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
        "INSERT OR REPLACE INTO kv_store (k, v, updated_at) VALUES (?, ?, ?)",
        (key, json.dumps(value), updated_at),
    )
