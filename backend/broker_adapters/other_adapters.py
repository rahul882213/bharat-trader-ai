"""Upstox v2, Angel One SmartAPI, and DhanHQ v2 Broker Adapters."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict

from .base import BrokerAdapter


class UpstoxAdapter(BrokerAdapter):
    broker_id = "upstox"
    broker_name = "Upstox API v2"
    is_live = True

    def __init__(self):
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def _req(self, method: str, path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"available": False, "broker": self.broker_name, "error": "UPSTOX_ACCESS_TOKEN not configured."}
        try:
            data = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(f"https://api.upstox.com/v2{path}", data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"available": True, "broker": self.broker_name, "data": json.loads(resp.read().decode("utf-8"))}
        except Exception as exc:
            return {"available": False, "broker": self.broker_name, "error": str(exc)}

    def get_portfolio(self) -> Dict[str, Any]:
        return self._req("GET", "/user/get-funds-and-margin")

    def get_holdings(self) -> Dict[str, Any]:
        return self._req("GET", "/portfolio/long-term-holdings")

    def get_positions(self) -> Dict[str, Any]:
        return self._req("GET", "/portfolio/short-term-positions")

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return self._req("POST", "/order/place", order)

    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self._req("PUT", "/order/modify", {"order_id": order_id, **updates})

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._req("DELETE", f"/order/cancel?order_id={order_id}")

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/order/details?order_id={order_id}")


class AngelOneAdapter(BrokerAdapter):
    broker_id = "angel_one"
    broker_name = "Angel One SmartAPI"
    is_live = True

    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY", "").strip()
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "").strip()
        self.jwt = os.getenv("ANGEL_JWT_TOKEN", "").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.client_id and self.jwt)

    def _not_configured(self) -> Dict[str, Any]:
        return {
            "available": False,
            "broker": self.broker_name,
            "error": "Angel One SmartAPI credentials (ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_JWT_TOKEN) not configured.",
        }

    def get_portfolio(self) -> Dict[str, Any]:
        return self._not_configured() if not self.is_configured() else {"available": True, "broker": self.broker_name, "data": {}}

    def get_holdings(self) -> Dict[str, Any]:
        return self._not_configured() if not self.is_configured() else {"available": True, "broker": self.broker_name, "data": []}

    def get_positions(self) -> Dict[str, Any]:
        return self._not_configured() if not self.is_configured() else {"available": True, "broker": self.broker_name, "data": []}

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return self._not_configured()

    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self._not_configured()

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._not_configured()

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._not_configured()


class DhanAdapter(BrokerAdapter):
    broker_id = "dhan"
    broker_name = "DhanHQ API v2"
    is_live = True

    def __init__(self):
        self.client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.access_token)

    def _req(self, method: str, path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"available": False, "broker": self.broker_name, "error": "DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN not configured."}
        try:
            data = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {
                "access-token": self.access_token,
                "client-id": self.client_id,
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(f"https://api.dhan.co/v2{path}", data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"available": True, "broker": self.broker_name, "data": json.loads(resp.read().decode("utf-8"))}
        except Exception as exc:
            return {"available": False, "broker": self.broker_name, "error": str(exc)}

    def get_portfolio(self) -> Dict[str, Any]:
        return self._req("GET", "/fundlimit")

    def get_holdings(self) -> Dict[str, Any]:
        return self._req("GET", "/holdings")

    def get_positions(self) -> Dict[str, Any]:
        return self._req("GET", "/positions")

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return self._req("POST", "/orders", order)

    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self._req("PUT", f"/orders/{order_id}", updates)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._req("DELETE", f"/orders/{order_id}")

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/orders/{order_id}")
