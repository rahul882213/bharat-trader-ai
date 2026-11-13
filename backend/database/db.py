"""Bharat Trader AI — Database Layer (SQLite default, PostgreSQL ready)."""
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
    # Default local SQLite path; if sqlite:///... parse path
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
