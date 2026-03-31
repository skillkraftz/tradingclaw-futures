"""Result persistence helpers."""
from __future__ import annotations

import sqlite3

from openclaw_futures.models import TradeIdea
from openclaw_futures.storage.ideas import record_result


def record_trade_result(
    connection: sqlite3.Connection,
    idea_id: int,
    *,
    result: str,
    exit_fill: float | None = None,
    pnl_dollars: float | None = None,
    notes: str | None = None,
) -> TradeIdea:
    return record_result(
        connection,
        idea_id,
        result=result,
        exit_fill=exit_fill,
        pnl_dollars=pnl_dollars,
        notes=notes,
    )
