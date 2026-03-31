"""File-backed provider for JSON and CSV fixtures."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from openclaw_futures.analysis.m6e_levels import build_m6e_snapshot
from openclaw_futures.analysis.mcl_levels import build_mcl_snapshot
from openclaw_futures.models import Bar, MarketSnapshot
from openclaw_futures.providers.base import MarketDataProvider


class FileMarketDataProvider(MarketDataProvider):
    """Load snapshots from JSON or derive them from CSV bars."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = symbol.upper()
        json_path = self.data_dir / f"{normalized.lower()}_snapshot.json"
        if json_path.exists():
            return self._load_snapshot_json(json_path)

        csv_path = self.data_dir / f"{normalized.lower()}_bars.csv"
        if csv_path.exists():
            bars = self._load_bars_csv(csv_path)
            if normalized == "MCL":
                return build_mcl_snapshot(bars)
            if normalized == "M6E":
                return build_m6e_snapshot(bars)
        raise FileNotFoundError(f"no fixture found for symbol={normalized!r} in {self.data_dir}")

    def _load_snapshot_json(self, path: Path) -> MarketSnapshot:
        payload = json.loads(path.read_text(encoding="utf-8"))
        bars = [Bar(**bar) for bar in payload.get("bars", [])]
        return MarketSnapshot(
            symbol=payload["symbol"],
            bars=bars,
            overnight_high=payload.get("overnight_high"),
            overnight_low=payload.get("overnight_low"),
            prior_day_high=payload.get("prior_day_high"),
            prior_day_low=payload.get("prior_day_low"),
            daily_open=payload.get("daily_open"),
            last_price=payload.get("last_price"),
            atr=payload.get("atr"),
            invalidation_high=payload.get("invalidation_high"),
            invalidation_low=payload.get("invalidation_low"),
            notes=payload.get("notes", []),
        )

    def _load_bars_csv(self, path: Path) -> list[Bar]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            bars = []
            for row in reader:
                bars.append(
                    Bar(
                        ts=row["ts"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                    )
                )
        return bars
