"""Base Market Data Provider Interface & Provenance Models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MarketDataProvider(ABC):
    provider_id: str = "base"
    provider_label: str = "Base Provider"
    is_unofficial: bool = False
    is_delayed: bool = True

    @abstractmethod
    def get_candles(
        self, symbol: str, interval: str = "1d", range_str: str = "6mo", exchange: str = "NSE"
    ) -> Dict[str, Any]:
        """Fetch OHLCV candles with source metadata and timestamps."""

    @abstractmethod
    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        """Fetch latest available quote with source metadata."""

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        """Optional fundamental data endpoint."""
        return {
            "available": False,
            "symbol": symbol,
            "exchange": exchange,
            "source": self.provider_label,
            "error": "Fundamentals not implemented by this provider.",
        }
