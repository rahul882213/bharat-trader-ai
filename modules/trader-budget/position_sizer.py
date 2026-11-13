"""Module 7: Position Size Calculator (Cash Equity & Optional F&O Lot Sizing)."""
from __future__ import annotations

from typing import Any, Dict

from backend.services.indian_charges import calculate_indian_charges


def calculate_position_size(
    capital_inr: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    segment: str = "cash_equity",
    trade_type: str = "equity_intraday",
    broker: str = "zerodha",
    lot_size: int = 1,
    fno_enabled: bool = False,
) -> Dict[str, Any]:
    """
    Calculate exact share/lot quantity accounting for Indian brokerage & statutory taxes.
    F&O is disabled by default unless explicitly enabled by the user.
    """
    if segment == "fno" and not fno_enabled:
        return {
            "allowed": False,
            "segment": "fno",
            "error": "F&O position sizing is disabled by default. Enable F&O explicitly in Risk Settings to size F&O contracts.",
        }

    if capital_inr <= 0 or entry_price <= 0 or stop_loss <= 0 or entry_price == stop_loss:
        return {
            "allowed": False,
            "error": "Capital, entry price, and stop-loss must be positive and entry must differ from stop-loss.",
        }

    max_risk_inr = capital_inr * (risk_pct / 100.0)
    risk_per_share = abs(entry_price - stop_loss)

    # Initial quantity purely from price risk, capped by affordable capital (or 1x notional for cash)
    raw_qty = int(max_risk_inr // risk_per_share)
    if segment == "cash_equity":
        max_notional_qty = int(capital_inr // entry_price)
        qty = min(raw_qty, max_notional_qty)
    else:
        # F&O lot rounding
        lots = max(int(raw_qty // max(lot_size, 1)), 0)
        qty = lots * max(lot_size, 1)

    # Iteratively adjust down if statutory charges + stop loss exceed max_risk_inr
    step = lot_size if segment == "fno" else 1
    charges = calculate_indian_charges(
        buy_price=min(entry_price, stop_loss),
        sell_price=max(entry_price, stop_loss),
        quantity=max(qty, 1),
        trade_type="fno_futures" if segment == "fno" else trade_type,
        broker=broker,
    )
    while qty > 0:
        charges = calculate_indian_charges(
            buy_price=entry_price,
            sell_price=stop_loss,
            quantity=qty,
            trade_type="fno_futures" if segment == "fno" else trade_type,
            broker=broker,
        )
        worst_case_loss = round(risk_per_share * qty + charges["total_charges"], 2)
        if worst_case_loss <= max_risk_inr or qty <= step:
            break
        qty -= step

    if qty <= 0:
        return {
            "allowed": False,
            "segment": segment,
            "error": "Calculated quantity is 0 under current risk budget and stop-loss distance.",
            "max_risk_budget_inr": round(max_risk_inr, 2),
        }

    final_charges = calculate_indian_charges(
        buy_price=entry_price,
        sell_price=stop_loss,
        quantity=qty,
        trade_type="fno_futures" if segment == "fno" else trade_type,
        broker=broker,
    )
    position_value = round(entry_price * qty, 2)
    actual_price_risk = round(risk_per_share * qty, 2)
    total_monetary_risk = round(actual_price_risk + final_charges["total_charges"], 2)

    return {
        "allowed": True,
        "currency": "INR",
        "segment": segment,
        "trade_type": "fno_futures" if segment == "fno" else trade_type,
        "capital_inr": round(capital_inr, 2),
        "risk_pct": risk_pct,
        "max_risk_budget_inr": round(max_risk_inr, 2),
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "risk_per_share_inr": round(risk_per_share, 2),
        "quantity": qty,
        "lots": (qty // max(lot_size, 1)) if segment == "fno" else None,
        "lot_size": lot_size if segment == "fno" else 1,
        "position_value_inr": position_value,
        "capital_utilization_pct": round((position_value / capital_inr) * 100.0, 2),
        "price_risk_inr": actual_price_risk,
        "estimated_charges_inr": final_charges["total_charges"],
        "charge_breakdown": final_charges,
        "total_monetary_risk_inr": total_monetary_risk,
    }
