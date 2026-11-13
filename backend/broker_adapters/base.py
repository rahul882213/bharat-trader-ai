"""Abstract Broker Adapter Interface for Indian Brokers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BrokerAdapter(ABC):
    broker_id: str = "base"
    broker_name: str = "Base Broker"
    is_live: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required environment credentials are present."""

    @abstractmethod
    def get_portfolio(self) -> Dict[str, Any]:
        """Retrieve cash margins and account summary in INR."""

    @abstractmethod
    def get_holdings(self) -> Dict[str, Any]:
        """Retrieve CNC delivery holdings."""

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """Retrieve open intraday/positional positions."""

    @abstractmethod
    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order (BUY/SELL)."""

    @abstractmethod
    def modify_order(self, order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Modify an existing open order."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing open order."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Fetch status of an order by ID."""
