from __future__ import annotations

from openclaw_futures.integrations.tc_command import run_tc_command


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append((method, path, payload))
        key = (method, path)
        if key not in self.responses:
            raise RuntimeError(f"missing fake response for {method} {path}")
        return self.responses[key]


def test_help_and_invalid_command_output() -> None:
    output = run_tc_command("help", client=FakeClient({}))
    invalid = run_tc_command("levels", client=FakeClient({}))
    assert "TradingClaw Commands" in output
    assert "tc scan test [account_size]" in output
    assert "TradingClaw Command Error" in invalid
    assert "tc result 3 win 50" in invalid


def test_scan_test_command_forces_expected_backend_flags() -> None:
    client = FakeClient(
        {
            ("POST", "/scan/run"): {
                "watchlist": ["EUR/USD"],
                "alert_window_active": False,
                "detected": 1,
                "persisted_ideas": 1,
                "alerted_ideas": 0,
                "alert_failures": 1,
                "idea_ids": [7],
                "webhook": {"reason": "webhook disabled"},
                "symbols": {
                    "EUR/USD": {
                        "valid_setups": 1,
                        "persisted_ideas": 1,
                        "alerted_idea_ids": [],
                    }
                },
            }
        }
    )
    output = run_tc_command("scan test 1500", client=client)
    assert client.calls == [
        (
            "POST",
            "/scan/run",
            {
                "account_size": 1500.0,
                "persist_ideas": True,
                "post_webhook": True,
                "allow_outside_window": True,
            },
        )
    ]
    assert "TradingClaw Test Scan" in output
    assert "forced: outside-window override on | persist on | webhook on" in output
    assert "idea ids: 7" in output


def test_sync_status_and_stats_output_are_compact() -> None:
    client = FakeClient(
        {
            ("GET", "/sync/status"): {
                "watchlist": ["EUR/USD", "SPY"],
                "last_sync_time": "2026-03-31T09:00:00-04:00",
                "last_sync_summary": {"fetched_bars": 120, "stored_changes": 8},
                "symbols": {
                    "EUR/USD": {"interval": "1min", "latest_cached_timestamp": "2026-03-31 09:00:00", "stored_changes": 4},
                    "SPY": {"interval": "5min", "latest_cached_timestamp": "2026-03-31 09:00:00", "stored_changes": 4},
                },
            },
            ("GET", "/stats"): {
                "stats": {
                    "total_ideas": 5,
                    "detected": 2,
                    "alerted": 1,
                    "taken": 1,
                    "skipped": 1,
                    "invalidated": 0,
                    "wins": 1,
                    "losses": 0,
                    "breakeven": 0,
                    "realized_pnl": 50.0,
                    "average_pnl": 50.0,
                }
            },
        }
    )
    sync_output = run_tc_command("sync status", client=client)
    stats_output = run_tc_command("stats", client=client)
    assert "TradingClaw Sync Status" in sync_output
    assert "fetched: 120 | stored: 8" in sync_output
    assert "TradingClaw Stats" in stats_output
    assert "ideas 5 | detected 2 | alerted 1 | taken 1" in stats_output


def test_ideas_and_result_output_show_real_backend_state() -> None:
    client = FakeClient(
        {
            ("GET", "/ideas"): {
                "ideas": [
                    {"idea_id": 3, "symbol": "EUR/USD", "bias": "long", "rr": 3.0, "status": "detected", "alert_sent": False, "alert_error": None},
                    {"idea_id": 4, "symbol": "SPY", "bias": "short", "rr": 3.0, "status": "alerted", "alert_sent": True, "alert_error": None},
                ]
            },
            ("GET", "/ideas/3"): {
                "idea": {"idea_id": 3, "symbol": "EUR/USD", "bias": "long", "rr": 3.0, "status": "detected", "alert_sent": False, "alert_error": "http_error"},
                "actions": [{"action_type": "detected", "acted_at": "2026-03-31T09:00:00-04:00", "pnl_dollars": None}],
            },
            ("POST", "/ideas/3/result"): {
                "idea": {"idea_id": 3, "symbol": "EUR/USD", "bias": "long", "rr": 3.0, "status": "win", "alert_sent": False, "alert_error": "http_error"},
            },
        }
    )
    ideas_output = run_tc_command("ideas", client=client)
    idea_output = run_tc_command("idea 3", client=client)
    result_output = run_tc_command("result 3 win 50", client=client)
    assert "TradingClaw Ideas" in ideas_output
    assert "#3 EUR/USD long | RR 3.00 | status detected | not alerted" in ideas_output
    assert "#4 SPY short | RR 3.00 | status alerted" in ideas_output
    assert "TradingClaw Idea" in idea_output
    assert "last action:" in idea_output
    assert "TradingClaw Result" in result_output
    assert "#3 EUR/USD long | RR 3.00 | status win | alert failed" in result_output


def test_backend_error_is_returned_without_generic_advice() -> None:
    class ErrorClient:
        def request(self, method: str, path: str, payload=None):
            raise RuntimeError("TradingClaw API error 404: unknown idea_id=999")

    output = run_tc_command("idea 999", client=ErrorClient())
    assert output.startswith("TradingClaw Error")
    assert "unknown idea_id=999" in output
