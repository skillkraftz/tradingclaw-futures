from __future__ import annotations

from openclaw_futures.integrations.openclaw_adapter import USAGE, _handle_command


def test_adapter_usage_for_empty_and_invalid_prefix(app) -> None:
    assert _handle_command("", app) == USAGE
    assert "requires commands starting with 'tc'" in _handle_command("plan 1500", app)


def test_adapter_plan_and_stats(app) -> None:
    plan_output = _handle_command("tc plan 1500", app)
    stats_output = _handle_command("tc stats", app)
    assert "TradingClaw Plan" in plan_output
    assert "TradingClaw Stats" in stats_output


def test_adapter_idea_lifecycle_commands(app) -> None:
    app.dispatch("POST", "/plan", {"account_size": 1500, "persist_ideas": True})
    ideas_output = _handle_command("tc ideas", app)
    idea_output = _handle_command("tc idea 1", app)
    take_output = _handle_command("tc take 1 1", app)
    result_output = _handle_command("tc result 1 win 86", app)

    assert "TradingClaw Ideas" in ideas_output
    assert "TradingClaw Idea" in idea_output
    assert "status taken" in take_output
    assert "status win" in result_output


def test_adapter_skip_command(app) -> None:
    app.dispatch("POST", "/plan", {"account_size": 1500, "persist_ideas": True})
    skip_output = _handle_command("tc skip 1", app)
    assert "status skipped" in skip_output


def test_adapter_reports_api_errors(app) -> None:
    assert "command error" in _handle_command("tc idea 999", app)
    assert "command error" in _handle_command("tc take bad 1", app)
    assert "unsupported command" in _handle_command("tc levels", app)
