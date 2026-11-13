"""Database Initialization & Migration CLI for Bharat Trader AI (PostgreSQL / SQLite)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.database.db import ROOT_DIR, check_db_health, execute_sql, get_db_dialect, init_db
from backend.database.stock_master_db import sync_stock_master

IST = ZoneInfo("Asia/Kolkata")


def seed_initial_watchlist() -> int:
    wl_path = ROOT_DIR / "trader" / "watchlist.json"
    if not wl_path.exists():
        return 0
    try:
        data = json.loads(wl_path.read_text(encoding="utf-8"))
        items = data.get("watchlist", [])
    except Exception:
        return 0

    now = datetime.now(tz=IST).isoformat()
    count = 0
    for item in items:
        sym = str(item.get("symbol") or "").strip().upper()
        ex = str(item.get("exchange") or "NSE").strip().upper()
        sec = str(item.get("sector") or "Indian Equities").strip()
        if not sym:
            continue
        execute_sql(
            """
            INSERT INTO watchlists (symbol, exchange, sector, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, exchange) DO UPDATE SET sector = excluded.sector
            """,
            (sym, ex, sec, now),
        )
        count += 1
    return count


def initialize_database(force_sync: bool = False) -> dict:
    init_db(force=True)
    sync_res = sync_stock_master(force=force_sync)
    wl_seeded = seed_initial_watchlist()
    health = check_db_health()
    return {
        "dialect": get_db_dialect(),
        "stock_master": sync_res,
        "watchlist_seeded": wl_seeded,
        "health": health,
    }


if __name__ == "__main__":
    print(json.dumps(initialize_database(force_sync=False), indent=2))
