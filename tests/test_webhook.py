from __future__ import annotations

import json
from pathlib import Path

from conftest import call_app

from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_contracts import build_trade_plan
from openclaw_futures.integrations.webhook import build_webhook_url, post_message
from openclaw_futures.render.webhook_render import render_webhook_plan


def test_webhook_payload_format(provider) -> None:
    plan = build_trade_plan(provider, 10000, source_room="desk")
    rendered = render_webhook_plan(plan)
    assert "TradingClaw plan for desk" in rendered
    assert "RR 3.00" in rendered


def test_build_webhook_url_supports_thread_id() -> None:
    assert build_webhook_url("https://example.com/webhook", "") == "https://example.com/webhook"
    assert build_webhook_url("https://example.com/webhook", "1234") == "https://example.com/webhook?thread_id=1234"
    assert build_webhook_url("https://example.com/webhook?wait=true", "1234") == "https://example.com/webhook?wait=true&thread_id=1234"


def test_post_message_includes_thread_id_in_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("openclaw_futures.integrations.webhook.request.urlopen", fake_urlopen)
    config = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir="unused",  # type: ignore[arg-type]
        default_provider="file",
        db_path="unused",  # type: ignore[arg-type]
        webhook_url="https://example.com/webhook?wait=true",
        webhook_thread_id="98765",
        room_label="desk",
        log_level="INFO",
    )

    result = post_message(config, "hello")
    assert result["sent"] is True
    assert captured["url"] == "https://example.com/webhook?wait=true&thread_id=98765"
    assert captured["body"] == {"content": "hello"}


def test_post_message_handles_disabled_and_transport_errors(monkeypatch, fixture_dir, tmp_path) -> None:
    disabled = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=fixture_dir,
        default_provider="file",
        db_path=tmp_path / "db.sqlite3",
        webhook_url="",
        webhook_thread_id="",
        room_label="desk",
        log_level="INFO",
    )
    assert post_message(disabled, "hello")["sent"] is False

    def fake_urlopen(_http_request, timeout=None):
        raise OSError("boom")

    monkeypatch.setattr("openclaw_futures.integrations.webhook.request.urlopen", fake_urlopen)
    failing = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=fixture_dir,
        default_provider="file",
        db_path=tmp_path / "db.sqlite3",
        webhook_url="https://example.com/webhook",
        webhook_thread_id="thread-1",
        room_label="desk",
        log_level="INFO",
    )
    result = post_message(failing, "hello")
    assert result["sent"] is False
    assert "thread_id=thread-1" in result["url"]


def test_lifecycle_webhook_posting_and_disabled_mode(app, monkeypatch) -> None:
    captured: list[tuple[str, str]] = []

    def fake_post_message(config, content):
        captured.append((config.webhook_url, content))
        return {"enabled": True, "sent": True}

    app.config = AppConfig(
        host=app.config.host,
        port=app.config.port,
        data_dir=app.config.data_dir,
        default_provider=app.config.default_provider,
        db_path=Path(str(app.config.db_path)),
        webhook_url="https://example.com/webhook",
        webhook_thread_id="thread-1",
        room_label=app.config.room_label,
        log_level=app.config.log_level,
    )
    monkeypatch.setattr("openclaw_futures.api.routes.post_message", fake_post_message)

    _, payload = call_app(app, "POST", "/plan", {"account_size": 10000, "persist_ideas": True})
    first, second = payload["idea_ids"]
    take_status, take_payload = call_app(app, "POST", f"/ideas/{first}/take", {"contracts": 1, "post_webhook": True})
    skip_status, skip_payload = call_app(app, "POST", f"/ideas/{second}/skip", {"post_webhook": True})

    app.config = AppConfig(
        host=app.config.host,
        port=app.config.port,
        data_dir=app.config.data_dir,
        default_provider=app.config.default_provider,
        db_path=Path(str(app.config.db_path)),
        webhook_url="",
        webhook_thread_id="",
        room_label=app.config.room_label,
        log_level=app.config.log_level,
    )
    monkeypatch.setattr("openclaw_futures.api.routes.post_message", post_message)
    _, payload = call_app(app, "POST", "/plan", {"account_size": 10000, "persist_ideas": True})
    third = payload["idea_ids"][0]
    disabled_status, disabled_payload = call_app(app, "POST", f"/ideas/{third}/invalidate", {"post_webhook": True})

    assert take_status == 200
    assert skip_status == 200
    assert disabled_status == 200
    assert "webhook" in take_payload
    assert "webhook" in skip_payload
    assert disabled_payload["webhook"]["sent"] is False
    assert len(captured) == 2
    assert "status taken" in captured[0][1]
    assert "status skipped" in captured[1][1]
