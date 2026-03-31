"""Stats and journal summaries."""
from __future__ import annotations

import sqlite3

from openclaw_futures.models import (
    IDEA_STATUS_ALERTED,
    IDEA_STATUS_BREAKEVEN,
    IDEA_STATUS_DETECTED,
    IDEA_STATUS_INVALIDATED,
    IDEA_STATUS_LOSS,
    IDEA_STATUS_PROPOSED,
    IDEA_STATUS_SKIPPED,
    IDEA_STATUS_TAKEN,
    IDEA_STATUS_WIN,
    StatsSummary,
)


def calculate_stats(connection: sqlite3.Connection) -> StatsSummary:
    rows = connection.execute("SELECT status, COUNT(*) AS count FROM trade_ideas GROUP BY status").fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    pnl_row = connection.execute(
        "SELECT COALESCE(SUM(pnl_dollars), 0.0) AS realized_pnl, COALESCE(AVG(pnl_dollars), 0.0) AS average_pnl FROM trade_actions WHERE pnl_dollars IS NOT NULL"
    ).fetchone()
    return StatsSummary(
        total_ideas=sum(counts.values()),
        detected=counts.get(IDEA_STATUS_DETECTED, 0) + counts.get(IDEA_STATUS_PROPOSED, 0),
        alerted=counts.get(IDEA_STATUS_ALERTED, 0),
        taken=counts.get(IDEA_STATUS_TAKEN, 0),
        skipped=counts.get(IDEA_STATUS_SKIPPED, 0),
        invalidated=counts.get(IDEA_STATUS_INVALIDATED, 0),
        wins=counts.get(IDEA_STATUS_WIN, 0),
        losses=counts.get(IDEA_STATUS_LOSS, 0),
        breakeven=counts.get(IDEA_STATUS_BREAKEVEN, 0),
        realized_pnl=round(pnl_row["realized_pnl"], 2),
        average_pnl=round(pnl_row["average_pnl"], 2),
    )
