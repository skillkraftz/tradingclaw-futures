from __future__ import annotations

import csv
import json
from datetime import datetime
from io import StringIO

import pytest

from conftest import call_app

from openclaw_futures.config import AppConfig
from openclaw_futures.models import Bar
from openclaw_futures.providers.twelvedata_provider import (
    TwelveDataEmptyResponseError,
    TwelveDataProvider,
    TwelveDataUnsupportedIntervalError,
)
from openclaw_futures.services.scanner import ScannerService
from openclaw_futures.storage.market_bars import fetch_recent_market_bars, get_latest_cached_timestamp


def _load_fixture_bars(fixture_dir, count: int | None = None) -> list[Bar]:
    with (fixture_dir / "m6e_bars.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        bars = [
            Bar(
                ts=row["ts"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for row in reader
        ]
    return bars if count is None else bars[:count]


class FakeLiveProvider:
    def __init__(self, responses: list[tuple[str, list[Bar], str]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def fetch_preferred_bars(
        self,
        *,
        symbol: str,
        start_at: str | None = None,
        end_at: str | None = None,
        interval_override: str | None = None,
        preferred_intervals: tuple[str, ...] | None = None,
    ):
        self.calls.append(
            {
                "symbol": symbol,
                "start_at": start_at,
                "end_at": end_at,
                "interval_override": interval_override,
                "preferred_intervals": preferred_intervals,
            }
        )
        return self.responses.pop(0)


def test_first_run_backfill_and_incremental_sync(connection, config, fixture_dir) -> None:
    initial = _load_fixture_bars(fixture_dir, count=20)
    incremental = initial[-2:] + [
        Bar(ts="2026-03-31 12:05:00", open=1.0830, high=1.0834, low=1.0828, close=1.0832, volume=1200),
        Bar(ts="2026-03-31 12:10:00", open=1.0832, high=1.0835, low=1.0829, close=1.0833, volume=1220),
    ]
    fake = FakeLiveProvider([("1min", initial, "EUR/USD"), ("1min", incremental, "EUR/USD")])
    scanner = ScannerService(config, connection, live_provider=fake)  # type: ignore[arg-type]

    first = scanner.run_sync(now=datetime(2026, 3, 31, 8, 45))
    second = scanner.run_sync(now=datetime(2026, 3, 31, 8, 50))

    assert first["last_sync_summary"]["sync_mode"] == "backfill"
    assert first["last_sync_summary"]["stored_changes"] == len(initial)
    assert second["last_sync_summary"]["sync_mode"] == "incremental"
    assert second["last_sync_summary"]["stored_changes"] == 2
    assert fake.calls[1]["start_at"] == initial[-1].ts
    assert get_latest_cached_timestamp(connection, symbol="M6E", interval="1min") == "2026-03-31 12:10:00"


def test_sync_status_and_scan_uses_cached_bars(connection, config, fixture_dir) -> None:
    bars = _load_fixture_bars(fixture_dir)
    fake = FakeLiveProvider([("1min", bars, "EUR/USD")])
    scanner = ScannerService(config, connection, live_provider=fake)  # type: ignore[arg-type]
    scanner.run_sync(now=datetime(2026, 3, 31, 8, 40))

    sync_status = scanner.get_sync_status(now=datetime(2026, 3, 31, 8, 41))
    scan = scanner.run_scan(account_size=10_000, now=datetime(2026, 3, 31, 9, 0))
    scan_status = scanner.get_scan_status(now=datetime(2026, 3, 31, 9, 1))

    assert sync_status["interval"] == "1min"
    assert sync_status["latest_cached_timestamp"] == bars[-1].ts
    assert scan["plan"]["levels"]["M6E"]["last_price"] == bars[-1].close
    assert scan["last_scan_result_summary"]["bars_used"] == len(fetch_recent_market_bars(connection, symbol="M6E", interval="1min"))
    assert scan_status["last_scan_result_summary"]["bars_used"] == scan["last_scan_result_summary"]["bars_used"]


def test_alert_window_blocks_persist_without_override(connection, fixture_dir, db_path) -> None:
    config = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=fixture_dir,
        default_provider="file",
        db_path=db_path,
        webhook_url="",
        webhook_thread_id="",
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
        allow_outside_window_manual_scan=False,
        live_symbol="M6E",
        live_symbol_map={"M6E": "EUR/USD"},
    )
    bars = _load_fixture_bars(fixture_dir)
    scanner = ScannerService(config, connection, live_provider=FakeLiveProvider([("1min", bars, "EUR/USD")]))  # type: ignore[arg-type]
    scanner.run_sync(now=datetime(2026, 3, 31, 8, 40))

    blocked = scanner.run_scan(persist_ideas=True, post_webhook_flag=True, now=datetime(2026, 3, 31, 12, 15))
    allowed = scanner.run_scan(
        persist_ideas=True,
        post_webhook_flag=False,
        allow_outside_window=True,
        now=datetime(2026, 3, 31, 12, 20),
    )

    assert blocked["alert_window_active"] is False
    assert blocked["persisted"] is False
    assert blocked["webhook"]["sent"] is False
    assert allowed["persisted"] is True
    assert allowed["manual_override_used"] is True


def test_api_sync_and_scan_endpoints(app, fixture_dir, monkeypatch) -> None:
    bars = _load_fixture_bars(fixture_dir)
    app.scanner.live_provider = FakeLiveProvider([("1min", bars, "EUR/USD")])  # type: ignore[assignment]
    monkeypatch.setattr(app.scanner, "_now", lambda _value=None: datetime(2026, 3, 31, 9, 0))

    sync_status, sync_payload = call_app(app, "POST", "/sync/run", {"days": 5})
    status_status, status_payload = call_app(app, "GET", "/sync/status")
    scan_status, scan_payload = call_app(app, "POST", "/scan/run", {"persist_ideas": True, "allow_outside_window": True})
    scan_info_status, scan_info_payload = call_app(app, "GET", "/scan/status")

    assert sync_status == 200
    assert sync_payload["backfill_days"] == 5
    assert status_status == 200
    assert status_payload["interval"] == "1min"
    assert scan_status == 200
    assert scan_payload["persisted"] is True
    assert scan_info_status == 200
    assert scan_info_payload["last_scan_result_summary"]["bars_used"] > 0


def test_twelvedata_provider_success_and_fallback(monkeypatch) -> None:
    def fake_request_json(self, _path, params):
        if params["interval"] == "1min":
            return {
                "values": [
                    {"datetime": "2026-03-31 08:00:00", "open": "1.08", "high": "1.09", "low": "1.07", "close": "1.085", "volume": "100"},
                    {"datetime": "2026-03-31 08:01:00", "open": "1.085", "high": "1.091", "low": "1.08", "close": "1.086", "volume": "110"},
                ]
            }
        raise TwelveDataUnsupportedIntervalError("1min unavailable")

    provider = TwelveDataProvider(api_key="test-key")
    monkeypatch.setattr(TwelveDataProvider, "_request_json", fake_request_json)
    bars = provider.fetch_bars(symbol="M6E", interval="1min")
    assert len(bars) == 2
    assert bars[0].ts == "2026-03-31 08:00:00"

    def fake_fetch_bars(self, *, symbol, interval, start_at=None, end_at=None):
        if interval == "1min":
            raise TwelveDataEmptyResponseError("empty")
        return [Bar(ts="2026-03-31 08:00:00", open=1.08, high=1.09, low=1.07, close=1.085, volume=0)]

    monkeypatch.setattr(TwelveDataProvider, "fetch_bars", fake_fetch_bars)
    interval, fallback_bars, provider_symbol = provider.fetch_preferred_bars(symbol="M6E")
    assert interval == "5min"
    assert len(fallback_bars) == 1
    assert provider_symbol == "EUR/USD"


def test_twelvedata_provider_missing_key_and_malformed_response(monkeypatch) -> None:
    provider = TwelveDataProvider(api_key="")
    with pytest.raises(Exception):
        provider.fetch_bars(symbol="M6E", interval="1min")

    payload = StringIO(json.dumps({"meta": {"symbol": "EUR/USD"}})).getvalue()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return payload.encode("utf-8")

    def fake_urlopen(_request, timeout=15):
        return FakeResponse()

    monkeypatch.setattr("openclaw_futures.providers.twelvedata_provider.request.urlopen", fake_urlopen)
    provider = TwelveDataProvider(api_key="test-key")
    with pytest.raises(Exception):
        provider.fetch_bars(symbol="M6E", interval="1min")
