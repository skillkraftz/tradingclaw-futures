from __future__ import annotations

import json
import subprocess
from pathlib import Path

from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_bridge import run_bridge_command
from openclaw_futures.integrations.openclaw_client import OpenClawClient
from openclaw_futures.integrations.reasoning_payloads import build_reasoning_payload
from openclaw_futures.models import StatsSummary


def test_openclaw_client_disabled_and_config() -> None:
    config = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=Path("tests/fixtures"),
        default_provider="file",
        db_path=Path("data/runtime/test.sqlite3"),
        webhook_url="",
        webhook_thread_id="",
        webhook_user_agent="TradingClaw/0.1 (private use; local trading engine)",
        room_label="desk",
        log_level="INFO",
        twelvedata_api_key="test-key",
        twelvedata_base_url="https://api.twelvedata.com",
        backfill_days=10,
        sync_start="08:00",
        sync_end="13:00",
        alert_start="08:30",
        alert_end="11:30",
        scan_interval_minutes=5,
        allow_outside_window_manual_scan=True,
        live_symbol="M6E",
        live_symbol_map={"M6E": "EUR/USD"},
        twelvedata_symbols=("EUR/USD", "SPY", "BTC/USD", "ETH/USD"),
        primary_symbol="EUR/USD",
        openclaw_enabled=False,
        openclaw_base_url="http://127.0.0.1:18789",
        openclaw_reasoning_path="/reason",
        openclaw_auth_token="Bearer token",
        openclaw_auth_header="Authorization",
    )
    client = OpenClawClient.from_config(config)
    result = client.submit_reasoning({"hello": "world"})
    assert result["enabled"] is False
    assert result["sent"] is False


def test_openclaw_client_success_and_http_error(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"summary": "ok"}).encode("utf-8")

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["headers"] = dict(http_request.header_items())
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("openclaw_futures.integrations.openclaw_client.request.urlopen", fake_urlopen)
    client = OpenClawClient(
        enabled=True,
        base_url="http://127.0.0.1:18789",
        reasoning_path="/reason",
        auth_token="Bearer token",
        auth_header="Authorization",
    )
    result = client.submit_reasoning({"hello": "world"})
    assert result["sent"] is True
    assert captured["url"] == "http://127.0.0.1:18789/reason"
    assert captured["body"] == {"hello": "world"}
    assert "Authorization" in captured["headers"]


def test_reasoning_payload_generation() -> None:
    payload = build_reasoning_payload(
        command="scan run",
        tradingclaw_response={
            "symbols": {"EUR/USD": {"valid_setups": 1}},
            "ideas": [{"idea_id": 7}],
            "stats": {"total_ideas": 3},
            "reasoning_context": {"account_size": 10000},
        },
        stats=StatsSummary(
            total_ideas=3,
            detected=1,
            alerted=1,
            taken=1,
            skipped=0,
            invalidated=0,
            wins=1,
            losses=0,
            breakeven=0,
            realized_pnl=86.0,
            average_pnl=86.0,
        ),
    )
    assert payload["command"] == "scan run"
    assert payload["symbol_summary"]["EUR/USD"]["valid_setups"] == 1
    assert payload["stats"]["realized_pnl"] == 86.0
    assert payload["reasoning_context"]["account_size"] == 10000


def test_bridge_command_mapping_without_openclaw(monkeypatch, config) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class FakeTradingClawApiClient:
        def __init__(self, *_args, **_kwargs):
            pass

        @classmethod
        def from_config(cls, _config):
            return cls()

        def request(self, method, path, payload=None):
            calls.append((method, path, payload))
            return {"text": f"{method} {path}"}

    monkeypatch.setattr("openclaw_futures.integrations.openclaw_bridge.TradingClawApiClient", FakeTradingClawApiClient)
    output = run_bridge_command(["plan", "1500"], config=config)
    assert "POST /plan" in output
    assert calls == [("POST", "/plan", {"account_size": 1500.0})]


def test_bridge_reasoning_disabled_and_error(monkeypatch, config) -> None:
    class FakeTradingClawApiClient:
        @classmethod
        def from_config(cls, _config):
            return cls()

        def request(self, method, path, payload=None):
            return {"text": "TradingClaw Scan Status", "symbols": {"EUR/USD": {"bars_used": 10}}}

    class FakeOpenClawClient:
        @classmethod
        def from_config(cls, _config):
            return cls()

        @property
        def enabled(self):
            return True

        def submit_reasoning(self, payload, path=None):
            return {"enabled": True, "sent": False, "reason": "gateway error"}

    monkeypatch.setattr("openclaw_futures.integrations.openclaw_bridge.TradingClawApiClient", FakeTradingClawApiClient)
    monkeypatch.setattr("openclaw_futures.integrations.openclaw_bridge.OpenClawClient", FakeOpenClawClient)
    output = run_bridge_command(["--reason", "stats"], config=config)
    assert "TradingClaw Scan Status" in output
    assert "gateway error" in output


def test_startup_script_help_and_syntax() -> None:
    subprocess.run(["bash", "-n", "start_tradingclaw.sh"], check=True)
    result = subprocess.run(["bash", "start_tradingclaw.sh", "--help"], check=True, capture_output=True, text=True)
    assert "--skip-tests" in result.stdout
    assert "--provider" in result.stdout
