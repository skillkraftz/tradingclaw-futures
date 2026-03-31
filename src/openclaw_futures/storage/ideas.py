"""Trade idea persistence and transitions."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from openclaw_futures.models import (
    IDEA_STATUS_BREAKEVEN,
    IDEA_STATUS_INVALIDATED,
    IDEA_STATUS_LOSS,
    IDEA_STATUS_PROPOSED,
    IDEA_STATUS_SKIPPED,
    IDEA_STATUS_TAKEN,
    IDEA_STATUS_WIN,
    TradeAction,
    TradeIdea,
)


def create_trade_idea(connection: sqlite3.Connection, *, source_room: str, setup) -> TradeIdea:
    notes_json = json.dumps(
        {
            "notes": list(setup.notes),
            "rejection_reasons": list(getattr(setup, "rejection_reasons", [])),
        }
    )
    cursor = connection.execute(
        """
        INSERT INTO trade_ideas (
            created_at, source_room, symbol, setup_type, bias, entry_min, entry_max, stop, target,
            risk_per_contract, reward_per_contract, rr, confidence, notes_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _now(),
            source_room,
            setup.symbol,
            setup.setup_type,
            setup.bias,
            setup.entry_min,
            setup.entry_max,
            setup.stop,
            setup.target,
            setup.risk_per_contract,
            setup.reward_per_contract,
            setup.rr,
            setup.confidence,
            notes_json,
            IDEA_STATUS_PROPOSED,
        ),
    )
    connection.commit()
    return get_trade_idea(connection, cursor.lastrowid)


def list_trade_ideas(connection: sqlite3.Connection, *, status: str | None = None, limit: int = 50) -> list[TradeIdea]:
    if status:
        rows = connection.execute(
            "SELECT * FROM trade_ideas WHERE status = ? ORDER BY idea_id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM trade_ideas ORDER BY idea_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_idea(row) for row in rows]


def get_trade_idea(connection: sqlite3.Connection, idea_id: int) -> TradeIdea:
    row = connection.execute("SELECT * FROM trade_ideas WHERE idea_id = ?", (idea_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown idea_id={idea_id}")
    return _row_to_idea(row)


def mark_taken(
    connection: sqlite3.Connection,
    idea_id: int,
    *,
    contracts: int | None = None,
    entry_fill: float | None = None,
    notes: str | None = None,
) -> TradeIdea:
    return _transition(
        connection,
        idea_id,
        from_status=IDEA_STATUS_PROPOSED,
        to_status=IDEA_STATUS_TAKEN,
        contracts=contracts,
        entry_fill=entry_fill,
        notes=notes,
    )


def mark_skipped(connection: sqlite3.Connection, idea_id: int, *, notes: str | None = None) -> TradeIdea:
    return _transition(connection, idea_id, from_status=IDEA_STATUS_PROPOSED, to_status=IDEA_STATUS_SKIPPED, notes=notes)


def mark_invalidated(connection: sqlite3.Connection, idea_id: int, *, notes: str | None = None) -> TradeIdea:
    return _transition(connection, idea_id, from_status=IDEA_STATUS_PROPOSED, to_status=IDEA_STATUS_INVALIDATED, notes=notes)


def record_result(
    connection: sqlite3.Connection,
    idea_id: int,
    *,
    result: str,
    exit_fill: float | None = None,
    pnl_dollars: float | None = None,
    notes: str | None = None,
) -> TradeIdea:
    if result not in {IDEA_STATUS_WIN, IDEA_STATUS_LOSS, IDEA_STATUS_BREAKEVEN}:
        raise ValueError("result must be one of: win, loss, breakeven")
    return _transition(
        connection,
        idea_id,
        from_status=IDEA_STATUS_TAKEN,
        to_status=result,
        exit_fill=exit_fill,
        pnl_dollars=pnl_dollars,
        notes=notes,
    )


def list_actions(connection: sqlite3.Connection, idea_id: int) -> list[TradeAction]:
    rows = connection.execute(
        "SELECT * FROM trade_actions WHERE idea_id = ? ORDER BY action_id ASC",
        (idea_id,),
    ).fetchall()
    return [_row_to_action(row) for row in rows]


def _transition(
    connection: sqlite3.Connection,
    idea_id: int,
    *,
    from_status: str,
    to_status: str,
    contracts: int | None = None,
    entry_fill: float | None = None,
    exit_fill: float | None = None,
    pnl_dollars: float | None = None,
    notes: str | None = None,
) -> TradeIdea:
    current = get_trade_idea(connection, idea_id)
    if current.status != from_status:
        raise ValueError(f"idea_id={idea_id} must be {from_status!r} before transition to {to_status!r}")
    connection.execute("UPDATE trade_ideas SET status = ? WHERE idea_id = ?", (to_status, idea_id))
    connection.execute(
        """
        INSERT INTO trade_actions (
            idea_id, acted_at, action_type, contracts, entry_fill, exit_fill, pnl_dollars, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (idea_id, _now(), to_status, contracts, entry_fill, exit_fill, pnl_dollars, notes),
    )
    connection.commit()
    return get_trade_idea(connection, idea_id)


def _row_to_idea(row: sqlite3.Row) -> TradeIdea:
    return TradeIdea(
        idea_id=row["idea_id"],
        created_at=row["created_at"],
        source_room=row["source_room"],
        symbol=row["symbol"],
        setup_type=row["setup_type"],
        bias=row["bias"],
        entry_min=row["entry_min"],
        entry_max=row["entry_max"],
        stop=row["stop"],
        target=row["target"],
        risk_per_contract=row["risk_per_contract"],
        reward_per_contract=row["reward_per_contract"],
        rr=row["rr"],
        confidence=row["confidence"],
        notes_json=json.loads(row["notes_json"]),
        status=row["status"],
    )


def _row_to_action(row: sqlite3.Row) -> TradeAction:
    return TradeAction(
        action_id=row["action_id"],
        idea_id=row["idea_id"],
        acted_at=row["acted_at"],
        action_type=row["action_type"],
        contracts=row["contracts"],
        entry_fill=row["entry_fill"],
        exit_fill=row["exit_fill"],
        pnl_dollars=row["pnl_dollars"],
        notes=row["notes"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
