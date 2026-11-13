"""Module 9: Price & Technical Alert Engine with Optional Telegram Webhook."""
from __future__ import annotations

import json
import os
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.data_providers.nse_master import normalize_symbol
from backend.data_providers.provider_manager import get_provider_manager
from backend.database.db import execute_sql, query_all
from backend.services.indicators import compute_all_indicators

IST = ZoneInfo("Asia/Kolkata")

ALERT_CONDITIONS = [
    "price_above",       # Price reaches entry / breakout
    "price_below",       # Price reaches stop-loss / breakdown
    "target_hit",        # Price reaches target
    "vwap_crossover",    # Price crosses above VWAP
    "volume_spike",      # Volume >= threshold * 20-bar avg (default 2.0x)
    "breakout",          # Close above 20-bar high
    "breakdown",         # Close below 20-bar low
    "unusual_volatility" # Candle range >= 2.2 * ATR14
]


def _send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=6):
            return True
    except Exception:
        return False


def create_alert(
    symbol: str,
    condition: str,
    threshold: Optional[float] = None,
    exchange: str = "NSE",
    telegram_notify: bool = False,
    message: str = "",
) -> Dict[str, Any]:
    alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(tz=IST).isoformat()
    sym = normalize_symbol(symbol)
    execute_sql(
        """
        INSERT INTO price_alerts (alert_id, symbol, exchange, condition, threshold, status, telegram_notify, created_at, message)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
        """,
        (alert_id, sym, exchange.upper(), condition, threshold, 1 if telegram_notify else 0, now, message),
    )
    return {"alert_id": alert_id, "symbol": sym, "condition": condition, "threshold": threshold, "status": "ACTIVE", "created_at": now}


def list_alerts() -> List[Dict[str, Any]]:
    return query_all("SELECT * FROM price_alerts ORDER BY created_at DESC")


def delete_alert(alert_id: str) -> Dict[str, Any]:
    execute_sql("DELETE FROM price_alerts WHERE alert_id = ?", (alert_id,))
    return {"deleted": True, "alert_id": alert_id}


def evaluate_alert_rule(alert: Dict[str, Any], candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candles:
        return {"triggered": False, "reason": "No candles"}
    ind = compute_all_indicators(candles)
    latest = ind["latest"]
    close = float(latest["close"])
    vwap_val = float(latest.get("vwap") or close)
    prev_vwap = float(ind["series"]["vwap"][-2] or vwap_val) if len(candles) >= 2 else vwap_val
    prev_close = float(candles[-2]["close"]) if len(candles) >= 2 else close
    vol_ratio = float(latest.get("volume_ratio") or 1.0)
    atr14 = float(latest.get("atr14") or (close * 0.015))
    c_range = float(candles[-1]["high"]) - float(candles[-1]["low"])

    cond = alert["condition"]
    thresh = float(alert["threshold"]) if alert.get("threshold") is not None else 0.0
    triggered = False
    reason = ""

    if cond in {"price_above", "entry_reached", "target_hit"}:
        triggered = close >= thresh
        reason = f"{alert['symbol']} reached ₹{close:.2f} (>= ₹{thresh:.2f})"
    elif cond in {"price_below", "stop_loss_hit"}:
        triggered = close <= thresh
        reason = f"{alert['symbol']} dropped to ₹{close:.2f} (<= ₹{thresh:.2f})"
    elif cond == "vwap_crossover":
        triggered = prev_close <= prev_vwap and close > vwap_val
        reason = f"{alert['symbol']} crossed above VWAP ₹{vwap_val:.2f} at ₹{close:.2f}"
    elif cond == "volume_spike":
        mult = thresh if thresh > 0 else 2.0
        triggered = vol_ratio >= mult
        reason = f"{alert['symbol']} volume spike {vol_ratio:.2f}x (>= {mult:.1f}x)"
    elif cond == "breakout" and len(candles) >= 21:
        hi20 = max(float(c["high"]) for c in candles[-21:-1])
        triggered = close > hi20
        reason = f"{alert['symbol']} closed at ₹{close:.2f} above 20-bar high ₹{hi20:.2f}"
    elif cond == "breakdown" and len(candles) >= 21:
        lo20 = min(float(c["low"]) for c in candles[-21:-1])
        triggered = close < lo20
        reason = f"{alert['symbol']} closed at ₹{close:.2f} below 20-bar low ₹{lo20:.2f}"
    elif cond == "unusual_volatility":
        mult = thresh if thresh > 0 else 2.2
        triggered = c_range >= mult * atr14
        reason = f"{alert['symbol']} bar range ₹{c_range:.2f} >= {mult:.1f}x ATR (₹{atr14:.2f})"

    return {"triggered": triggered, "price": close, "reason": reason}


def check_alerts() -> Dict[str, Any]:
    alerts = query_all("SELECT * FROM price_alerts WHERE status = 'ACTIVE'")
    pm = get_provider_manager()
    triggered_list: List[Dict[str, Any]] = []
    cache: Dict[str, Any] = {}

    for al in alerts:
        sym = al["symbol"]
        if sym not in cache:
            cache[sym] = pm.get_candles(sym, interval="1d", range_str="3mo", exchange=al.get("exchange", "NSE"))
        data = cache[sym]
        if not data.get("available"):
            continue
        res = evaluate_alert_rule(al, data["candles"])
        if res["triggered"]:
            now = datetime.now(tz=IST).isoformat()
            execute_sql(
                "UPDATE price_alerts SET status = 'TRIGGERED', last_triggered_at = ?, message = ? WHERE alert_id = ?",
                (now, res["reason"], al["alert_id"]),
            )
            tg_sent = False
            if al.get("telegram_notify"):
                tg_sent = _send_telegram(f"Bharat Trader AI Alert: {res['reason']}")
            triggered_list.append({**al, "triggered_at": now, "reason": res["reason"], "telegram_sent": tg_sent})

    return {
        "checked_count": len(alerts),
        "triggered_count": len(triggered_list),
        "triggered": triggered_list,
        "all_alerts": list_alerts(),
        "checked_at_ist": datetime.now(tz=IST).isoformat(),
    }
