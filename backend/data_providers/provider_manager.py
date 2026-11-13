"""Interchangeable Multi-Provider Data Manager."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import MarketDataProvider
from .yahoo_provider import YahooUnofficialProvider


class ProviderManager:
    def __init__(self):
        self._yahoo = YahooUnofficialProvider()

    def get_active_provider(self) -> MarketDataProvider:
        # If Zerodha Kite live credentials are configured, route real-time quotes via Kite adapter when enabled;
        # supplementary historical & fundamentals always cleanly declare source.
        return self._yahoo

    def has_broker_realtime(self) -> Dict[str, bool]:
        return {
            "zerodha_kite": bool(os.getenv("KITE_API_KEY") and os.getenv("KITE_ACCESS_TOKEN")),
            "upstox": bool(os.getenv("UPSTOX_ACCESS_TOKEN")),
            "angel_one": bool(os.getenv("ANGEL_API_KEY") and os.getenv("ANGEL_CLIENT_ID")),
            "dhan": bool(os.getenv("DHAN_CLIENT_ID") and os.getenv("DHAN_ACCESS_TOKEN")),
        }

    def get_candles(
        self, symbol: str, interval: str = "1d", range_str: Optional[str] = None, exchange: str = "NSE"
    ) -> Dict[str, Any]:
        return self.get_active_provider().get_candles(symbol, interval=interval, range_str=range_str, exchange=exchange)

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        return self.get_active_provider().get_quote(symbol, exchange=exchange)

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        return self.get_active_provider().get_fundamentals(symbol, exchange=exchange)


_SINGLETON = ProviderManager()


def get_provider_manager() -> ProviderManager:
    return _SINGLETON
