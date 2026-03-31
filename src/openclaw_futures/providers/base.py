"""Provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from openclaw_futures.models import MarketSnapshot


class MarketDataProvider(ABC):
    """Abstract market data provider."""

    @abstractmethod
    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Return a market snapshot for a supported symbol."""
