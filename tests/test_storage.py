from __future__ import annotations

from pathlib import Path

from openclaw_futures.integrations.openclaw_contracts import build_trade_plan
from openclaw_futures.storage.db import connect
from openclaw_futures.storage.ideas import create_trade_idea, list_trade_ideas, mark_invalidated, mark_skipped, mark_taken
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

    mark_taken(connection, 1, contracts=1, entry_fill=idea.entry_min)
    final = record_trade_result(connection, 1, result="loss", pnl_dollars=-45.0)
    assert final.status == "loss"


def test_all_status_transitions(connection, provider) -> None:
    plan = build_trade_plan(provider, 10000, source_room="desk")
    first = create_trade_idea(connection, source_room="desk", setup=plan.setups[0])
    second = create_trade_idea(connection, source_room="desk", setup=plan.setups[1])
    third = create_trade_idea(connection, source_room="desk", setup=plan.setups[0])
    fourth = create_trade_idea(connection, source_room="desk", setup=plan.setups[1])

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
    assert stats.proposed == 1
