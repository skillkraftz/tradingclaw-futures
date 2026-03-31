from __future__ import annotations

import json

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
