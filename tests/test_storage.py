from __future__ import annotations

from pathlib import Path

from openclaw_futures.integrations.openclaw_contracts import build_trade_plan
from openclaw_futures.storage.db import connect
from openclaw_futures.storage.ideas import (
    create_trade_idea,
    list_trade_ideas,
    mark_invalidated,
    mark_skipped,
    mark_taken,
    record_alert_state,
)
from openclaw_futures.storage.results import record_trade_result
from openclaw_futures.storage.stats import calculate_stats


def test_sqlite_initialization(connection) -> None:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('trade_ideas', 'trade_actions')"
    ).fetchall()
    assert {row["name"] for row in tables} == {"trade_ideas", "trade_actions"}


def test_db_connect_creates_missing_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "runtime" / "journal.sqlite3"
    connection = connect(db_path)
    try:
        assert db_path.parent.exists()
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('trade_ideas', 'trade_actions')"
        ).fetchall()
        assert {row["name"] for row in tables} == {"trade_ideas", "trade_actions"}
    finally:
        connection.close()


def test_idea_and_result_persistence(connection, provider) -> None:
    plan = build_trade_plan(provider, 10000, source_room="desk")
    idea = create_trade_idea(connection, source_room="desk", setup=plan.setups[0])
    assert idea.idea_id == 1
    assert idea.source_room == "desk"
    assert idea.status == "detected"
    assert idea.alert_sent is False

    mark_taken(connection, 1, contracts=1, entry_fill=idea.entry_min)
    final = record_trade_result(connection, 1, result="loss", pnl_dollars=-45.0)
    assert final.status == "loss"


def test_all_status_transitions(connection, provider) -> None:
    plan = build_trade_plan(provider, 10000, source_room="desk")
    first = create_trade_idea(connection, source_room="desk", setup=plan.setups[0])
    second = create_trade_idea(connection, source_room="desk", setup=plan.setups[1])
    third = create_trade_idea(connection, source_room="desk", setup=plan.setups[0], dedupe_today=False)
    fourth = create_trade_idea(connection, source_room="desk", setup=plan.setups[1], dedupe_today=False)

    assert mark_skipped(connection, first.idea_id, notes="pass").status == "skipped"
    assert mark_invalidated(connection, second.idea_id, notes="invalid").status == "invalidated"
    assert mark_taken(connection, third.idea_id, contracts=1, entry_fill=third.entry_min).status == "taken"
    assert record_trade_result(connection, third.idea_id, result="win", pnl_dollars=67.5).status == "win"
    assert mark_taken(connection, fourth.idea_id, contracts=1, entry_fill=fourth.entry_min).status == "taken"
    assert record_trade_result(connection, fourth.idea_id, result="breakeven", pnl_dollars=0).status == "breakeven"


def test_stats_calculation(connection, provider) -> None:
    plan = build_trade_plan(provider, 10000)
    create_trade_idea(connection, source_room="desk", setup=plan.setups[0])
    ideas = list_trade_ideas(connection)
    assert ideas
    stats = calculate_stats(connection)
    assert stats.total_ideas == 1
    assert stats.detected == 1
    assert stats.alerted == 0


def test_alert_state_persistence_and_legacy_migration(connection, provider) -> None:
    plan = build_trade_plan(provider, 10000, source_room="desk")
    idea = create_trade_idea(connection, source_room="desk", setup=plan.setups[0])

    updated = record_alert_state(
        connection,
        [idea.idea_id],
        result={"sent": False, "reason_code": "webhook_disabled", "reason": "webhook disabled"},
        alert_channel="desk",
        attempted_at="2026-03-31T09:00:00+00:00",
    )[0]
    assert updated.status == "detected"
    assert updated.alert_error == "webhook_disabled: webhook disabled"

    alerted = record_alert_state(
        connection,
        [idea.idea_id],
        result={"sent": True},
        alert_channel="desk",
        attempted_at="2026-03-31T09:05:00+00:00",
    )[0]
    assert alerted.status == "alerted"
    assert alerted.alert_sent is True
    assert alerted.alerted_at == "2026-03-31T09:05:00+00:00"

    connection.execute(
        """
        INSERT INTO trade_ideas (
            created_at, source_room, symbol, setup_type, bias, entry_min, entry_max, stop, target,
            risk_per_contract, reward_per_contract, rr, confidence, notes_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-03-31T09:00:00+00:00",
            "desk",
            idea.symbol,
            idea.setup_type,
            idea.bias,
            idea.entry_min,
            idea.entry_max,
            idea.stop,
            idea.target,
            idea.risk_per_contract,
            idea.reward_per_contract,
            idea.rr,
            idea.confidence,
            '{"notes": [], "rejection_reasons": []}',
            "proposed",
        ),
    )
    from openclaw_futures.storage.db import initialize

    initialize(connection)
    migrated = list_trade_ideas(connection, limit=10)[0]
    assert migrated.status == "detected"
    assert migrated.alert_sent is False
