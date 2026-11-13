"""Module 8: Indian Broker Integration & Human-in-the-Loop Order Executor."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.broker_adapters.other_adapters import AngelOneAdapter, DhanAdapter, UpstoxAdapter
from backend.broker_adapters.paper_adapter import PaperBrokerAdapter
from backend.broker_adapters.zerodha_kite import ZerodhaKiteAdapter
from backend.services.indian_charges import calculate_indian_charges


def get_adapter(broker: str = "paper"):
    b = (broker or "paper").lower().strip()
    if b in {"zerodha", "kite"}:
        return ZerodhaKiteAdapter()
    if b == "upstox":
        return UpstoxAdapter()
    if b in {"angel", "angel_one"}:
        return AngelOneAdapter()
    if b == "dhan":
        return DhanAdapter()
    return PaperBrokerAdapter()


def get_broker_status() -> Dict[str, Any]:
    paper_default = os.getenv("TRADING_MODE", "paper").lower() != "live"
    adapters = [ZerodhaKiteAdapter(), UpstoxAdapter(), AngelOneAdapter(), DhanAdapter()]
    return {
        "default_mode": "paper" if paper_default else "live_guarded",
        "paper_trading_enabled": True,
        "require_explicit_approval_for_live": True,
        "brokers": [
            {
                "id": a.broker_id,
                "name": a.broker_name,
                "configured": a.is_configured(),
                "supports_live": a.is_live,
                "login_url": a.get_login_url() if hasattr(a, "get_login_url") else None,
            }
            for a in adapters
        ],
    }


def preview_live_order(order: Dict[str, Any]) -> Dict[str, Any]:
    """Build mandatory 7-point pre-execution summary before any live broker order."""
    qty = int(order.get("quantity", 0))
    entry = float(order.get("price", 0.0))
    sl = float(order.get("stop_loss", 0.0))
    target = float(order.get("target", 0.0))
    product = order.get("product", "MIS").upper()
    trade_type = "equity_delivery" if product == "CNC" else "equity_intraday"
    chg = calculate_indian_charges(entry, sl if sl > 0 else entry, max(qty, 1), trade_type=trade_type)
    max_loss = round(abs(entry - sl) * qty + chg["total_charges"], 2) if sl > 0 else round(entry * qty, 2)

    return {
        "requires_explicit_confirmation": True,
        "order_summary": {
            "symbol": order.get("symbol", "").upper(),
            "exchange": order.get("exchange", "NSE").upper(),
            "side": order.get("side", "BUY").upper(),
            "product": product,
            "order_type": order.get("order_type", "LIMIT").upper(),
            "broker": order.get("broker", "zerodha"),
        },
        "quantity": qty,
        "entry_price_inr": round(entry, 2),
        "stop_loss_inr": round(sl, 2),
        "target_inr": round(target, 2),
        "maximum_estimated_loss_inr": max_loss,
        "estimated_charges_inr": chg["total_charges"],
        "confirmation_prompt": (
            f"CONFIRM LIVE ORDER: {order.get('side','BUY').upper()} {qty} {order.get('symbol','').upper()} "
            f"@ ₹{entry:.2f} | SL ₹{sl:.2f} | Target ₹{target:.2f} | Max Est. Loss ₹{max_loss:,.2f}"
        ),
    }


def execute_order(
    order: Dict[str, Any],
    mode: str = "paper",
    broker: str = "paper",
    explicit_user_approval: bool = False,
) -> Dict[str, Any]:
    """
    Execute order. Paper trading is default.
    Live execution is strictly blocked unless mode == 'live' AND explicit_user_approval is True.
    """
    if mode.lower() != "live" or broker.lower() == "paper":
        return PaperBrokerAdapter().place_order(order)

    preview = preview_live_order({**order, "broker": broker})
    if not explicit_user_approval:
        return {
            "executed": False,
            "blocked_reason": "LIVE ORDER BLOCKED: Explicit user approval is mandatory before live broker dispatch.",
            "approval_preview": preview,
        }

    adapter = get_adapter(broker)
    if not adapter.is_configured():
        return {
            "executed": False,
            "blocked_reason": f"{adapter.broker_name} credentials are not configured in environment variables.",
            "approval_preview": preview,
        }

    res = adapter.place_order(order)
    return {
        "executed": bool(res.get("available")),
        "mode": "live",
        "broker": adapter.broker_name,
        "approval_preview": preview,
        "broker_response": res,
    }


def get_portfolio_summary(broker: str = "paper", fetch_ltp: bool = False) -> Dict[str, Any]:
    if broker.lower() == "paper":
        p = PaperBrokerAdapter()
        return {
            "portfolio": p.get_portfolio(),
            "positions": p.get_positions(fetch_ltp=fetch_ltp)["positions"],
            "holdings": p.get_holdings()["holdings"],
            **p.get_orders_and_journal(),
        }
    adapter = get_adapter(broker)
    return {
        "portfolio": adapter.get_portfolio(),
        "positions": adapter.get_positions(),
        "holdings": adapter.get_holdings(),
    }
