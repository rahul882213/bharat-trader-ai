"""Zerodha Kite Connect v3 Adapter (Environment-Credentialed, No Hardcoded Secrets)."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .base import BrokerAdapter

KITE_BASE_URL = "https://api.kite.trade"


class ZerodhaKiteAdapter(BrokerAdapter):
    broker_id = "zerodha"
    broker_name = "Zerodha Kite Connect"
    is_live = True

    def __init__(self):
        self.api_key = os.getenv("KITE_API_KEY", "").strip()
        self.api_secret = os.getenv("KITE_API_SECRET", "").strip()
        self.access_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.access_token)

    def get_login_url(self) -> str:
        if not self.api_key:
            return ""
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={urllib.parse.quote(self.api_key)}"

    def generate_session_checksum(self, request_token: str) -> str:
        raw = f"{self.api_key}{request_token}{self.api_secret}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _request(self, method: str, path: str, form_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "available": False,
                "broker": self.broker_name,
                "error": "Zerodha Kite Connect credentials (KITE_API_KEY, KITE_ACCESS_TOKEN) are not set in environment variables.",
            }
        url = f"{KITE_BASE_URL}{path}"
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }
        data_bytes = None
        if form_data is not None:
            data_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                return {"available": True, "broker": self.broker_name, "data": parsed.get("data")}
        except Exception as exc:
            return {"available": False, "broker": self.broker_name, "error": str(exc)}

    def get_portfolio(self) -> Dict[str, Any]:
        return self._request("GET", "/user/margins")

    def get_holdings(self) -> Dict[str, Any]:
        return self._request("GET", "/portfolio/holdings")

    def get_positions(self) -> Dict[str, Any]:
        return self._request("GET", "/portfolio/positions")

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        inst = urllib.parse.quote(f"{exchange.upper()}:{symbol.upper()}")
        return self._request("GET", f"/quote?i={inst}")

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "exchange": order.get("exchange", "NSE").upper(),
            "tradingsymbol": order["symbol"].upper(),
            "transaction_type": order["side"].upper(),
            "quantity": int(order["quantity"]),
            "product": order.get("product", "MIS").upper(),
            "order_type": order.get("order_type", "LIMIT").upper(),
            "price": float(order.get("price", 0.0)),
            "validity": order.get("validity", "DAY"),
        }
        return self._request("POST", "/orders/regular", form_data=payload)

    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/orders/regular/{urllib.parse.quote(order_id)}", form_data=updates)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/orders/regular/{urllib.parse.quote(order_id)}")

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/orders/{urllib.parse.quote(order_id)}")
