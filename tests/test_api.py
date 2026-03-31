from __future__ import annotations

from conftest import call_app


def test_health_endpoint(app) -> None:
    status, payload = call_app(app, "GET", "/health")
    assert status == 200
    assert payload["status"] == "ok"


def test_help_endpoint_output(app) -> None:
    status, payload = call_app(app, "GET", "/help")
    assert status == 200
    assert "manual only" in payload["help"]
    assert "/reasoning-context" in payload["help"]
    assert "does not manage OpenClaw" in payload["help"]


def test_plan_and_idea_lifecycle(app) -> None:
    status, payload = call_app(app, "POST", "/plan", {"account_size": 10000, "persist_ideas": True})
    assert status == 200
    assert payload["idea_ids"]

    idea_id = payload["idea_ids"][0]
    take_status, take_payload = call_app(app, "POST", f"/ideas/{idea_id}/take", {"contracts": 1, "entry_fill": 72.18})
    assert take_status == 200
    assert take_payload["idea"]["status"] == "taken"

    result_status, result_payload = call_app(
        app,
        "POST",
        f"/ideas/{idea_id}/result",
        {"result": "win", "exit_fill": 72.63, "pnl_dollars": 135.0},
    )
    assert result_status == 200
    assert result_payload["idea"]["status"] == "win"


def test_reasoning_context_response_shape(app) -> None:
    status, payload = call_app(app, "POST", "/reasoning-context", {"account_size": 12000, "symbols": ["MCL"]})
    context = payload["reasoning_context"]
    assert status == 200
    assert context["account_size"] == 12000
    assert context["requested_symbols"] == ["MCL"]
    assert "valid_setups" in context
    assert "rejected_setups" in context
    assert "major_levels" in context
    assert "invalidation_zones" in context
    assert "contract_sizing_summary" in context


def test_operation_without_webhook_configured(app) -> None:
    status, payload = call_app(app, "POST", "/plan", {"account_size": 10000, "post_webhook": True})
    assert status == 200
    assert payload["webhook"]["sent"] is False


def test_unknown_route_returns_404(app) -> None:
    status, payload = call_app(app, "GET", "/missing")
    assert status == 404
    assert "unknown route" in payload["error"]
