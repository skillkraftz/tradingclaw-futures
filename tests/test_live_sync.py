from __future__ import annotations

import csv
import json
from datetime import datetime

import pytest

from conftest import call_app

from openclaw_futures.config import AppConfig
from openclaw_futures.models import AccountPlan, Bar, ContractAllocation, SetupCandidate, TradePlan
from openclaw_futures.providers.twelvedata_provider import (
    TwelveDataEmptyResponseError,
    TwelveDataMalformedResponseError,
    TwelveDataProvider,
)
from openclaw_futures.services.scanner import ScannerService
from openclaw_futures.storage.market_bars import get_latest_cached_timestamp


WATCHLIST = ("EUR/USD", "SPY", "BTC/USD", "ETH/USD")


def _load_fixture_bars(fixture_dir) -> list[Bar]:
    with (fixture_dir / "m6e_bars.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
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


def _scaled_bars(base_bars: list[Bar], *, factor: float, offset: float = 0.0) -> list[Bar]:
    return [
        Bar(
            ts=bar.ts,
            open=round((bar.open * factor) + offset, 5 if factor < 10 else 2),
            high=round((bar.high * factor) + offset, 5 if factor < 10 else 2),
            low=round((bar.low * factor) + offset, 5 if factor < 10 else 2),
            close=round((bar.close * factor) + offset, 5 if factor < 10 else 2),
            volume=bar.volume,
        )
        for bar in base_bars
    ]


def _watchlist_bars(fixture_dir) -> dict[str, list[Bar]]:
    base = _load_fixture_bars(fixture_dir)
    return {
        "EUR/USD": base,
        "SPY": _scaled_bars(base, factor=400.0, offset=-350.0),
        "BTC/USD": _scaled_bars(base, factor=40000.0, offset=-41000.0),
        "ETH/USD": _scaled_bars(base, factor=2500.0, offset=-2600.0),
    }


class FakeBatchProvider:
    def __init__(self, responses: list[dict[str, dict[str, object]]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def fetch_preferred_bars_many(self, *, symbols, start_times, end_at=None, preferred_intervals=None):
        self.calls.append(
            {
                "symbols": list(symbols),
                "start_times": dict(start_times),
                "end_at": end_at,
                "preferred_intervals": preferred_intervals,
            }
        )
        return self.responses.pop(0)


def _provider_payload(interval: str, bars_by_symbol: dict[str, list[Bar]]) -> dict[str, dict[str, object]]:
    return {
        symbol: {
            "interval": interval,
            "bars": bars,
            "provider_symbol": symbol,
        }
        for symbol, bars in bars_by_symbol.items()
    }


def test_first_run_backfill_and_incremental_sync_multiple_symbols(connection, config, fixture_dir) -> None:
    first_batch = _watchlist_bars(fixture_dir)
    second_batch = {
        symbol: bars[-2:] + [Bar(ts="2026-03-31 12:05:00", open=bars[-1].open, high=bars[-1].high, low=bars[-1].low, close=bars[-1].close, volume=1200)]
        for symbol, bars in first_batch.items()
    }
    provider = FakeBatchProvider([_provider_payload("1min", first_batch), _provider_payload("1min", second_batch)])
    scanner = ScannerService(config, connection, live_provider=provider)  # type: ignore[arg-type]

    first = scanner.run_sync(now=datetime(2026, 3, 31, 8, 45))
    second = scanner.run_sync(now=datetime(2026, 3, 31, 8, 50))

    assert first["watchlist"] == list(WATCHLIST)
    assert first["symbols"]["EUR/USD"]["stored_changes"] == len(first_batch["EUR/USD"])
    assert second["symbols"]["SPY"]["stored_changes"] == 1
    assert provider.calls[1]["start_times"]["BTC/USD"] == first_batch["BTC/USD"][-1].ts
    assert get_latest_cached_timestamp(connection, symbol="ETH/USD", interval="1min") == "2026-03-31 12:05:00"


def test_sync_status_and_scan_group_results(connection, config, fixture_dir) -> None:
    bars = _watchlist_bars(fixture_dir)
    scanner = ScannerService(config, connection, live_provider=FakeBatchProvider([_provider_payload("1min", bars)]))  # type: ignore[arg-type]
    scanner.run_sync(now=datetime(2026, 3, 31, 8, 40))

    sync_status = scanner.get_sync_status(now=datetime(2026, 3, 31, 8, 41))
    scan = scanner.run_scan(account_size=10_000, now=datetime(2026, 3, 31, 9, 0))
    scan_status = scanner.get_scan_status(now=datetime(2026, 3, 31, 9, 1))

    assert sync_status["watchlist"] == list(WATCHLIST)
    assert sync_status["symbols"]["BTC/USD"]["interval"] == "1min"
    assert scan["symbols"]["SPY"]["category"] == "equity/etf"
    assert scan["symbols"]["ETH/USD"]["plan"]["levels"]["ETH/USD"]["last_price"] == bars["ETH/USD"][-1].close
    assert scan_status["symbols"]["EUR/USD"]["last_scan_summary"]["bars_used"] > 0
    assert scan_status["last_scan_result_summary"]["detected_ideas"] >= 0


def test_per_symbol_dedupe_and_manual_override(connection, fixture_dir, db_path) -> None:
    config = AppConfig(
        host="127.0.0.1",
        port=8787,
        data_dir=fixture_dir,
        default_provider="file",
        db_path=db_path,
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
        allow_outside_window_manual_scan=False,
        live_symbol="M6E",
        live_symbol_map={"M6E": "EUR/USD"},
        twelvedata_symbols=WATCHLIST,
        primary_symbol="EUR/USD",
        openclaw_enabled=False,
        openclaw_base_url="http://127.0.0.1:18789",
        openclaw_reasoning_path="",
        openclaw_auth_token="",
        openclaw_auth_header="Authorization",
    )
    bars = _watchlist_bars(fixture_dir)
    scanner = ScannerService(config, connection, live_provider=FakeBatchProvider([_provider_payload("1min", bars)]))  # type: ignore[arg-type]
    scanner.run_sync(now=datetime(2026, 3, 31, 8, 40))

    blocked = scanner.run_scan(persist_ideas=True, post_webhook_flag=True, now=datetime(2026, 3, 31, 12, 15))
    allowed = scanner.run_scan(
        persist_ideas=True,
        allow_outside_window=True,
        now=datetime(2026, 3, 31, 12, 20),
    )
    deduped = scanner.run_scan(
        persist_ideas=True,
        allow_outside_window=True,
        now=datetime(2026, 3, 31, 12, 25),
    )

    assert blocked["persisted"] is False
    assert blocked["webhook"]["sent"] is False
    assert blocked["webhook"]["reason_code"] == "alert_suppressed_policy"
    assert allowed["manual_override_used"] is True
    assert deduped["idea_ids"] == []


def test_scan_records_failed_alert_state_and_counts(connection, config, fixture_dir) -> None:
    bars = _watchlist_bars(fixture_dir)
    scanner = ScannerService(config, connection, live_provider=FakeBatchProvider([_provider_payload("1min", bars)]))  # type: ignore[arg-type]
    scanner.run_sync(now=datetime(2026, 3, 31, 8, 40))

    from openclaw_futures.services import scanner as scanner_module

    original = scanner_module.post_message
    original_build_trade_plan = scanner_module.build_trade_plan

    def fake_build_trade_plan(_provider, account_size, symbols=None, source_room="desk"):
        symbol = (symbols or ["EUR/USD"])[0]
        setup = SetupCandidate(
            symbol=symbol,
            bias="long",
            entry_min=1.08,
            entry_max=1.081,
            stop=1.079,
            target=1.084,
            risk_per_contract=10.0,
            reward_per_contract=30.0,
            rr=3.0,
            confidence=0.8,
            setup_type="pullback",
            notes=["test setup"],
            valid=True,
            score=10,
        )
        return TradePlan(
            account_plan=AccountPlan(
                account_size=account_size,
                risk_percent=1.0,
                risk_budget=100.0,
                daily_loss_cap=200.0,
                max_open_risk=100.0,
                allocations=[
                    ContractAllocation(
                        label="base",
                        total_contracts=1,
                        mcl_contracts=0,
                        m6e_contracts=1,
                        estimated_risk=10.0,
                        estimated_reward=30.0,
                    )
                ],
                notes=[],
            ),
            setups=[setup],
            rejected_setups=[],
            do_not_trade_conditions=[],
            level_summary={symbol: scanner_module._snapshot_from_bars(symbol, bars[symbol])},
            source_room=source_room,
        )

    scanner_module.post_message = lambda _config, _content: {
        "enabled": True,
        "attempted": True,
        "sent": False,
        "reason_code": "http_error",
        "reason": "HTTP 500: upstream failure",
    }
    scanner_module.build_trade_plan = fake_build_trade_plan
    try:
        payload = scanner.run_scan(
            account_size=10_000,
            persist_ideas=True,
            post_webhook_flag=True,
            now=datetime(2026, 3, 31, 9, 0),
        )
    finally:
        scanner_module.post_message = original
        scanner_module.build_trade_plan = original_build_trade_plan

    assert payload["persisted_ideas"] > 0
    assert payload["alerted_ideas"] == 0
    assert payload["alert_failures"] == payload["persisted_ideas"]
    assert payload["webhook"]["reason_code"] == "http_error"
    assert "HTTP 500" in payload["last_scan_result_summary"]["alert_reason"]
    assert any(idea["alert_error"] for idea in payload["ideas"])


def test_api_sync_and_scan_status_for_watchlist(app, fixture_dir, monkeypatch) -> None:
    bars = _watchlist_bars(fixture_dir)
    app.scanner.live_provider = FakeBatchProvider([_provider_payload("1min", bars)])  # type: ignore[assignment]
    monkeypatch.setattr(app.scanner, "_now", lambda _value=None: datetime(2026, 3, 31, 9, 0))

    sync_status, sync_payload = call_app(app, "POST", "/sync/run", {"days": 5})
    status_status, status_payload = call_app(app, "GET", "/sync/status")
    scan_status, scan_payload = call_app(app, "POST", "/scan/run", {"persist_ideas": True, "allow_outside_window": True})
    scan_info_status, scan_info_payload = call_app(app, "GET", "/scan/status")

    assert sync_status == 200
    assert sync_payload["watchlist"] == list(WATCHLIST)
    assert status_status == 200
    assert "SPY" in status_payload["symbols"]
    assert scan_status == 200
    assert "BTC/USD" in scan_payload["symbols"]
    assert scan_info_status == 200
    assert scan_info_payload["symbols"]["ETH/USD"]["last_scan_summary"]["bars_used"] > 0


def test_twelvedata_provider_batch_request_and_mixed_results(monkeypatch) -> None:
    provider = TwelveDataProvider(
        api_key="test-key",
        symbol_map={symbol: symbol for symbol in WATCHLIST},
    )

    def fake_request_json(self, _path, params):
        assert params["symbol"] == ",".join(WATCHLIST)
        return {
            "EUR/USD": {
                "values": [{"datetime": "2026-03-31 08:00:00", "open": "1.08", "high": "1.09", "low": "1.07", "close": "1.085", "volume": "100"}]
            },
            "SPY": {
                "values": [{"datetime": "2026-03-31 08:00:00", "open": "520", "high": "521", "low": "519", "close": "520.5", "volume": "100"}]
            },
            "BTC/USD": {
                "values": [{"datetime": "2026-03-31 08:00:00", "open": "70000", "high": "70100", "low": "69900", "close": "70050", "volume": "100"}]
            },
            "ETH/USD": {"meta": {"symbol": "ETH/USD"}},
        }

    monkeypatch.setattr(TwelveDataProvider, "_request_json", fake_request_json)
    results, errors = provider.fetch_bars_batch(symbols=list(WATCHLIST), interval="1min", start_at="2026-03-31 08:00:00")
    assert set(results) == {"EUR/USD", "SPY", "BTC/USD"}
    assert "ETH/USD" in errors


def test_twelvedata_provider_multi_symbol_fallback(monkeypatch) -> None:
    provider = TwelveDataProvider(
        api_key="test-key",
        symbol_map={symbol: symbol for symbol in WATCHLIST},
    )

    def fake_fetch_bars_batch(self, *, symbols, interval, start_at=None, end_at=None):
        if interval == "1min":
            return {}, {symbol: TwelveDataEmptyResponseError("empty") for symbol in symbols}
        return (
            {
                symbol: [Bar(ts="2026-03-31 08:00:00", open=1.0, high=1.1, low=0.9, close=1.05, volume=0)]
                for symbol in symbols
            },
            {},
        )

    monkeypatch.setattr(TwelveDataProvider, "fetch_bars_batch", fake_fetch_bars_batch)
    results = provider.fetch_preferred_bars_many(
        symbols=list(WATCHLIST),
        start_times={symbol: "2026-03-31 08:00:00" for symbol in WATCHLIST},
    )
    assert all(result["interval"] == "5min" for result in results.values())


def test_twelvedata_provider_missing_key_and_batch_malformed(monkeypatch) -> None:
    provider = TwelveDataProvider(api_key="")
    with pytest.raises(Exception):
        provider.fetch_bars(symbol="EUR/USD", interval="1min")

    provider = TwelveDataProvider(api_key="test-key", symbol_map={symbol: symbol for symbol in WATCHLIST})
    monkeypatch.setattr(TwelveDataProvider, "_request_json", lambda self, _path, params: {"meta": {"symbol": "EUR/USD"}})
    with pytest.raises(TwelveDataMalformedResponseError):
        provider.fetch_bars_batch(symbols=list(WATCHLIST), interval="1min")
