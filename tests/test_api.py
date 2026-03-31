from __future__ import annotations

import io
import json

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


def test_setups_levels_account_and_stats_endpoints(app) -> None:
    setups_status, setups_payload = call_app(app, "POST", "/setups", {"account_size": 10000, "symbols": ["MCL"]})
    levels_status, levels_payload = call_app(app, "POST", "/levels", {"symbols": ["M6E"]})
    account_status, account_payload = call_app(app, "POST", "/account", {"account_size": 10000, "symbols": ["MCL", "M6E"]})
    stats_status, stats_payload = call_app(app, "GET", "/stats")
    assert setups_status == 200
    assert setups_payload["symbols"] == ["MCL"]
    assert levels_status == 200
    assert "M6E" in levels_payload["levels"]
    assert account_status == 200
    assert account_payload["account_plan"]["account_size"] == 10000
    assert stats_status == 200
    assert stats_payload["stats"]["total_ideas"] == 0


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


def test_skip_and_invalidate_endpoints(app) -> None:
    _, payload = call_app(app, "POST", "/plan", {"account_size": 10000, "persist_ideas": True})
    first, second = payload["idea_ids"]
    skip_status, skip_payload = call_app(app, "POST", f"/ideas/{first}/skip", {"notes": "pass"})
    invalidate_status, invalidate_payload = call_app(app, "POST", f"/ideas/{second}/invalidate", {"notes": "gone"})
    assert skip_status == 200
    assert skip_payload["idea"]["status"] == "skipped"
    assert invalidate_status == 200
    assert invalidate_payload["idea"]["status"] == "invalidated"


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


def test_invalid_json_returns_400(app) -> None:
    status_headers: dict[str, object] = {}

    def start_response(status: str, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/plan",
        "CONTENT_LENGTH": "5",
        "wsgi.input": io.BytesIO(b"{bad}"),
    }
    body = b"".join(app(environ, start_response))
    payload = json.loads(body.decode("utf-8"))
    assert str(status_headers["status"]).startswith("400")
    assert "invalid JSON body" in payload["error"]
