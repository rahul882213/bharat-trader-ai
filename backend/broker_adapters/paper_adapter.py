"""Paper Trading Broker Adapter (Default Safe Mode, SQLite + JSON Backed)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import get_symbol_sector, normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.database.db import execute_sql, get_kv, query_all
from backend.services.indian_charges import calculate_indian_charges

IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = Path(__file__).resolve().parents[2]
ORDERS_JSON = ROOT_DIR / "trader" / "orders.json"
HISTORY_JSON = ROOT_DIR / "trader" / "trade_history.json"
RISK_CONFIG_PATH = ROOT_DIR / "config" / "risk_config.json"


def get_risk_capital_safe() -> float:
    saved = get_kv("risk_config")
    if isinstance(saved, dict) and saved.get("total_capital_inr"):
        return float(saved["total_capital_inr"])
    if RISK_CONFIG_PATH.exists():
        with RISK_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return float(json.load(f).get("total_capital_inr", 1000000.0))
    return 1000000.0


def _sync_json_files() -> None:
    orders = query_all("SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 200")
    trades = query_all("SELECT * FROM trade_journal ORDER BY closed_at DESC LIMIT 200")
    realized = round(sum(float(t.get("net_pnl", 0.0)) for t in trades), 2)
    cap = get_risk_capital_safe()
    ORDERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with ORDERS_JSON.open("w", encoding="utf-8") as f:
        json.dump({"mode": "paper", "orders": orders}, f, indent=2)
    with HISTORY_JSON.open("w", encoding="utf-8") as f:
        json.dump({"currency": "INR", "initial_capital": cap, "realized_pnl": realized, "trades": trades}, f, indent=2)


class PaperBrokerAdapter:
    broker_id = "paper"
    broker_name = "Bharat Paper Trading Engine"
    is_live = False

    def is_configured(self) -> bool:
        return True

    def get_portfolio(self) -> Dict[str, Any]:
        initial_cap = get_risk_capital_safe()
        trades = query_all("SELECT net_pnl, charges_inr FROM trade_journal")
        realized_pnl = sum(float(t["net_pnl"]) for t in trades)
        total_charges = sum(float(t["charges_inr"]) for t in trades)
        positions = self.get_positions()["positions"]
        deployed = sum(float(p["avg_price"]) * int(p["quantity"]) for p in positions)
        unrealized = sum(float(p.get("unrealized_pnl", 0.0)) for p in positions)
        equity = initial_cap + realized_pnl + unrealized
        return {
            "available": True,
            "mode": "paper",
            "broker": self.broker_name,
            "currency": "INR",
            "initial_capital_inr": round(initial_cap, 2),
            "available_cash_inr": round(initial_cap + realized_pnl - deployed, 2),
            "deployed_margin_inr": round(deployed, 2),
            "realized_pnl_inr": round(realized_pnl, 2),
            "unrealized_pnl_inr": round(unrealized, 2),
            "total_equity_inr": round(equity, 2),
            "total_charges_paid_inr": round(total_charges, 2),
            "total_trades_closed": len(trades),
            "open_positions_count": len(positions),
            "updated_at_ist": datetime.now(tz=IST).isoformat(),
        }

    def get_holdings(self) -> Dict[str, Any]:
        rows = query_all("SELECT * FROM paper_positions WHERE product = 'CNC'")
        return {"available": True, "mode": "paper", "currency": "INR", "holdings": rows}

    def get_positions(self, fetch_ltp: bool = False) -> Dict[str, Any]:
        rows = query_all("SELECT * FROM paper_positions")
        pm = get_provider_manager() if fetch_ltp else None
        enriched: List[Dict[str, Any]] = []
        for p in rows:
            avg = float(p["avg_price"])
            qty = int(p["quantity"])
            ltp = avg
            ltp_source = "Cost Basis (Click Refresh Live LTP)"
            if pm:
                q = pm.get_quote(p["symbol"], exchange=p["exchange"])
                if q.get("available"):
                    ltp = float(q["price"])
                    ltp_source = q["source"]
            pnl = (ltp - avg) * qty if p["side"] == "BUY" else (avg - ltp) * qty
            enriched.append({
                **p,
                "ltp": round(ltp, 2),
                "ltp_source": ltp_source,
                "market_value_inr": round(ltp * qty, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round((pnl / (avg * qty)) * 100.0, 2) if avg * qty > 0 else 0.0,
            })
        return {"available": True, "mode": "paper", "currency": "INR", "positions": enriched}

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        sym = normalize_symbol(order["symbol"])
        exch = order.get("exchange", "NSE").upper()
        side = order["side"].upper()
        product = order.get("product", "MIS").upper()
        order_type = order.get("order_type", "LIMIT").upper()
        qty = int(order["quantity"])
        price = float(order["price"])
        sl = float(order["stop_loss"]) if order.get("stop_loss") else None
        target = float(order["target"]) if order.get("target") else None
        notes = order.get("notes", "")
        now = datetime.now(tz=IST).isoformat()
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"

        trade_type = "equity_delivery" if product == "CNC" else "equity_intraday"
        est_charges = calculate_indian_charges(price, price, qty, trade_type=trade_type)["total_charges"] / 2.0

        execute_sql(
            """
            INSERT INTO paper_orders
            (order_id, symbol, exchange, side, order_type, product, quantity, price, stop_loss, target, status, mode, charges_inr, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'paper', ?, ?, ?)
            """,
            (order_id, sym, exch, side, order_type, product, qty, price, sl, target, "FILLED", round(est_charges, 2), notes, now),
        )

        # Check existing position for netting/closing
        existing = query_all(
            "SELECT * FROM paper_positions WHERE symbol = ? AND exchange = ? AND product = ?",
            (sym, exch, product),
        )
        if not existing:
            execute_sql(
                """
                INSERT INTO paper_positions (symbol, exchange, product, side, quantity, avg_price, stop_loss, target, sector, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sym, exch, product, side, qty, price, sl, target, get_symbol_sector(sym), now),
            )
        else:
            pos = existing[0]
            pos_side = pos["side"]
            pos_qty = int(pos["quantity"])
            pos_avg = float(pos["avg_price"])
            if pos_side == side:
                new_qty = pos_qty + qty
                new_avg = ((pos_avg * pos_qty) + (price * qty)) / new_qty
                execute_sql(
                    "UPDATE paper_positions SET quantity = ?, avg_price = ?, stop_loss = COALESCE(?, stop_loss), target = COALESCE(?, target) WHERE symbol = ? AND exchange = ? AND product = ?",
                    (new_qty, round(new_avg, 2), sl, target, sym, exch, product),
                )
            else:
                close_qty = min(pos_qty, qty)
                buy_p = pos_avg if pos_side == "BUY" else price
                sell_p = price if pos_side == "BUY" else pos_avg
                chg = calculate_indian_charges(buy_p, sell_p, close_qty, trade_type=trade_type)
                trade_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
                execute_sql(
                    """
                    INSERT INTO trade_journal
                    (trade_id, symbol, exchange, strategy, side, quantity, entry_price, exit_price, gross_pnl, charges_inr, net_pnl, mode, opened_at, closed_at, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'paper', ?, ?, ?)
                    """,
                    (trade_id, sym, exch, order.get("strategy", "Discretionary"), pos_side, close_qty, pos_avg, price, chg["gross_pnl"], chg["total_charges"], chg["net_pnl"], pos["opened_at"], now, notes),
                )
                rem = pos_qty - close_qty
                if rem == 0:
                    execute_sql(
                        "DELETE FROM paper_positions WHERE symbol = ? AND exchange = ? AND product = ?",
                        (sym, exch, product),
                    )
                else:
                    execute_sql(
                        "UPDATE paper_positions SET quantity = ? WHERE symbol = ? AND exchange = ? AND product = ?",
                        (rem, sym, exch, product),
                    )

        _sync_json_files()
        return {
            "available": True,
            "mode": "paper",
            "order_id": order_id,
            "status": "FILLED",
            "symbol": sym,
            "exchange": exch,
            "side": side,
            "quantity": qty,
            "price": price,
            "created_at_ist": now,
        }

    def close_position(self, symbol: str, exchange: str = "NSE", product: str = "MIS", exit_price: float | None = None) -> Dict[str, Any]:
        sym = normalize_symbol(symbol)
        rows = query_all(
            "SELECT * FROM paper_positions WHERE symbol = ? AND exchange = ? AND product = ?",
            (sym, exchange.upper(), product.upper()),
        )
        if not rows:
            return {"available": False, "error": f"No open paper position for {sym} ({product})."}
        pos = rows[0]
        price = exit_price
        if price is None:
            q = get_provider_manager().get_quote(sym, exchange=exchange)
            price = float(q["price"]) if q.get("available") else float(pos["avg_price"])
        opposite_side = "SELL" if pos["side"] == "BUY" else "BUY"
        return self.place_order({
            "symbol": sym,
            "exchange": exchange,
            "side": opposite_side,
            "product": product,
            "order_type": "MARKET",
            "quantity": int(pos["quantity"]),
            "price": price,
            "notes": "Position squared off",
        })

    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        execute_sql(
            "UPDATE paper_orders SET price = COALESCE(?, price), stop_loss = COALESCE(?, stop_loss), target = COALESCE(?, target) WHERE order_id = ?",
            (updates.get("price"), updates.get("stop_loss"), updates.get("target"), order_id),
        )
        _sync_json_files()
        return {"available": True, "order_id": order_id, "status": "MODIFIED"}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        execute_sql("UPDATE paper_orders SET status = 'CANCELLED' WHERE order_id = ?", (order_id,))
        _sync_json_files()
        return {"available": True, "order_id": order_id, "status": "CANCELLED"}

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        rows = query_all("SELECT * FROM paper_orders WHERE order_id = ?", (order_id,))
        if not rows:
            return {"available": False, "error": "Order not found"}
        return {"available": True, "order": rows[0]}

    def get_orders_and_journal(self) -> Dict[str, Any]:
        orders = query_all("SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 100")
        journal = query_all("SELECT * FROM trade_journal ORDER BY closed_at DESC LIMIT 100")
        return {"orders": orders, "journal": journal}
