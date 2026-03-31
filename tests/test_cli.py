from __future__ import annotations

import json

from openclaw_futures.cli import main


def test_cli_help_output(capsys) -> None:
    exit_code = main(["help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "TradingClaw Futures" in captured.out
    assert "/reasoning-context" in captured.out


def test_cli_reasoning_context_json(tmp_path, fixture_dir, monkeypatch, capsys) -> None:
    monkeypatch.setenv("TRADINGCLAW_DATA_DIR", str(fixture_dir))
    monkeypatch.setenv("TRADINGCLAW_DB_PATH", str(tmp_path / "runtime" / "journal.sqlite3"))
    exit_code = main(["reasoning-context", "--account-size", "10000", "--symbols", "MCL"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["requested_symbols"] == ["MCL"]
    assert "valid_setups" in payload


def test_cli_webhook_test_outputs_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "openclaw_futures.cli.post_message",
        lambda _config, message: {"sent": False, "reason_code": "webhook_disabled", "message": message},
    )
    exit_code = main(["webhook", "test", "--message", "ping"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["reason_code"] == "webhook_disabled"
    assert payload["message"] == "ping"
