"""Cached market-bar persistence helpers."""
from __future__ import annotations

import sqlite3

from openclaw_futures.models import Bar, MarketBar


def insert_market_bars(connection: sqlite3.Connection, bars: list[MarketBar]) -> int:
    if not bars:
        return 0
    cursor = connection.executemany(
        """
        INSERT INTO market_bars (
            symbol, interval, timestamp, open, high, low, close, volume, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, interval, timestamp) DO NOTHING
        """,
        [
            (
                bar.symbol,
                bar.interval,
                bar.ts,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.source,
            )
            for bar in bars
        ],
    )
    connection.commit()
    return cursor.rowcount


def fetch_recent_market_bars(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    interval: str,
    limit: int = 5000,
) -> list[Bar]:
    rows = connection.execute(
        """
        SELECT timestamp, open, high, low, close, COALESCE(volume, 0.0) AS volume
        FROM market_bars
        WHERE symbol = ? AND interval = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (symbol, interval, limit),
    ).fetchall()
    ordered = reversed(rows)
    return [
        Bar(
            ts=row["timestamp"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in ordered
    ]


def get_latest_cached_timestamp(connection: sqlite3.Connection, *, symbol: str, interval: str) -> str | None:
    row = connection.execute(
        "SELECT MAX(timestamp) AS latest_timestamp FROM market_bars WHERE symbol = ? AND interval = ?",
        (symbol, interval),
    ).fetchone()
    if row is None:
        return None
    return row["latest_timestamp"]


def needs_initial_backfill(connection: sqlite3.Connection, *, symbol: str, interval: str | None = None) -> bool:
    if interval is None:
        row = connection.execute(
            "SELECT 1 FROM market_bars WHERE symbol = ? LIMIT 1",
            (symbol,),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT 1 FROM market_bars WHERE symbol = ? AND interval = ? LIMIT 1",
            (symbol, interval),
        ).fetchone()
    return row is None


def list_cached_intervals(connection: sqlite3.Connection, *, symbol: str) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT interval FROM market_bars WHERE symbol = ? ORDER BY interval ASC",
        (symbol,),
    ).fetchall()
    return [row["interval"] for row in rows]
