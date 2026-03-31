"""Application service layer."""
from __future__ import annotations

from openclaw_futures.config import DEFAULT_SYMBOLS
from openclaw_futures.models import MarketSnapshot, SetupCandidate
from openclaw_futures.providers.base import MarketDataProvider


class OpenClawService:
    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def load_snapshots(self) -> list[MarketSnapshot]:
        return [self.provider.get_snapshot(symbol) for symbol in DEFAULT_SYMBOLS]

    def do_not_trade_conditions(
        self,
        snapshots: list[MarketSnapshot],
        setups: list[SetupCandidate],
    ) -> list[str]:
        conditions: list[str] = []
        for snapshot in snapshots:
            if snapshot.atr is None:
                conditions.append(f"{snapshot.symbol}: ATR unavailable.")
            elif snapshot.overnight_high is None or snapshot.overnight_low is None:
                conditions.append(f"{snapshot.symbol}: overnight range unavailable.")
            elif snapshot.invalidation_high is not None and snapshot.last_price is not None and snapshot.last_price > snapshot.invalidation_high:
                conditions.append(f"{snapshot.symbol}: price is above invalidation high.")
            elif snapshot.invalidation_low is not None and snapshot.last_price is not None and snapshot.last_price < snapshot.invalidation_low:
                conditions.append(f"{snapshot.symbol}: price is below invalidation low.")

        if not [setup for setup in setups if setup.valid]:
            conditions.append("No valid explicit 1:3 setups are available.")
        conditions.append("Stand aside after hitting the daily loss cap.")
        conditions.append("Do not chase entries outside the defined entry bands.")
        return conditions
