"""Cached live-data sync and scan service."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from openclaw_futures.analysis.live_levels import build_live_snapshot
from openclaw_futures.config import AppConfig, live_symbol_profile
from openclaw_futures.integrations.openclaw_contracts import build_trade_plan, idea_contract, plan_contract
from openclaw_futures.integrations.webhook import post_message, suppressed_result
from openclaw_futures.models import MarketBar, MarketSnapshot
from openclaw_futures.providers.base import MarketDataProvider
from openclaw_futures.providers.twelvedata_provider import TwelveDataProvider
from openclaw_futures.render.text_render import (
    render_scan_status,
    render_sync_status,
    render_window_state,
)
from openclaw_futures.render.webhook_render import render_webhook_scan
from openclaw_futures.storage.ideas import create_trade_idea, get_trade_idea, list_trade_ideas, record_alert_state
from openclaw_futures.storage.market_bars import (
    fetch_recent_market_bars,
    get_latest_cached_timestamp,
    insert_market_bars,
    list_cached_intervals,
    needs_initial_backfill,
)
from openclaw_futures.storage.runtime_state import get_state, set_state


NEW_YORK = ZoneInfo("America/New_York")


class ScannerService:
    def __init__(
        self,
        config: AppConfig,
        connection: sqlite3.Connection,
        live_provider: TwelveDataProvider | None = None,
    ) -> None:
        self.config = config
        self.connection = connection
        self.live_provider = live_provider or TwelveDataProvider.from_config(config)

    def run_sync(
        self,
        *,
        force_full_backfill: bool = False,
        days: int | None = None,
        interval_override: str | None = None,
        symbol_override: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        watchlist = [symbol_override] if symbol_override else list(self.config.twelvedata_symbols)
        current_time = self._now(now)
        backfill_days = days or self.config.backfill_days
        start_times: dict[str, str | None] = {}
        sync_modes: dict[str, str] = {}
        for symbol in watchlist:
            active_interval = interval_override or self._preferred_cached_interval(symbol)
            if force_full_backfill or active_interval is None or needs_initial_backfill(self.connection, symbol=symbol, interval=active_interval):
                start_times[symbol] = (current_time - timedelta(days=backfill_days)).strftime("%Y-%m-%d %H:%M:%S")
                sync_modes[symbol] = "backfill"
            else:
                start_times[symbol] = get_latest_cached_timestamp(self.connection, symbol=symbol, interval=active_interval)
                sync_modes[symbol] = "incremental"

        provider_results = self.live_provider.fetch_preferred_bars_many(
            symbols=watchlist,
            start_times=start_times,
            preferred_intervals=(interval_override,) if interval_override else ("1min", "5min"),
        )
        per_symbol: dict[str, dict[str, object]] = {}
        total_fetched = 0
        total_stored = 0
        for symbol in watchlist:
            result = provider_results[symbol]
            if "error" in result:
                active_interval = interval_override or self._preferred_cached_interval(symbol)
                per_symbol[symbol] = {
                    "category": live_symbol_profile(symbol).category,
                    "provider_symbol": self.live_provider.resolve_symbol(symbol),
                    "interval": active_interval,
                    "sync_mode": sync_modes[symbol],
                    "fetched_bars": 0,
                    "stored_changes": 0,
                    "latest_cached_timestamp": self._latest_cached_timestamp(symbol, active_interval),
                    "error": result["error"],
                }
                continue

            interval = str(result["interval"])
            bars = result["bars"]
            provider_symbol = str(result["provider_symbol"])
            inserted = insert_market_bars(
                self.connection,
                [
                    MarketBar(
                        symbol=symbol,
                        interval=interval,
                        ts=bar.ts,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        source="twelvedata",
                    )
                    for bar in bars
                ],
            )
            latest_cached_timestamp = get_latest_cached_timestamp(self.connection, symbol=symbol, interval=interval)
            total_fetched += len(bars)
            total_stored += inserted
            per_symbol[symbol] = {
                "category": live_symbol_profile(symbol).category,
                "provider_symbol": provider_symbol,
                "interval": interval,
                "sync_mode": sync_modes[symbol],
                "fetched_bars": len(bars),
                "stored_changes": inserted,
                "latest_cached_timestamp": latest_cached_timestamp,
            }

        payload = {
            "provider": "twelvedata",
            "watchlist": watchlist,
            "primary_symbol": self.config.primary_symbol,
            "backfill_days": backfill_days,
            "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
            "last_sync_time": current_time.isoformat(),
            "last_sync_summary": {
                "watchlist_size": len(watchlist),
                "fetched_bars": total_fetched,
                "stored_changes": total_stored,
                "window_active": self._is_sync_window_active(current_time),
            },
            "symbols": per_symbol,
        }
        payload["text"] = render_sync_status(payload)
        set_state(self.connection, _sync_key(None), payload)
        for symbol, details in per_symbol.items():
            set_state(
                self.connection,
                _sync_key(symbol),
                {
                    "provider": "twelvedata",
                    "watchlist": [symbol],
                    "primary_symbol": symbol,
                    "backfill_days": backfill_days,
                    "sync_window": payload["sync_window"],
                    "last_sync_time": current_time.isoformat(),
                    "last_sync_summary": details,
                    "symbols": {symbol: details},
                },
            )
        return payload

    def run_scheduled_cycle(
        self,
        *,
        account_size: float = 10_000,
        persist_ideas: bool = False,
        post_webhook_flag: bool = False,
        source_room: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current_time = self._now(now)
        payload: dict[str, object] = {
            "ran_sync": False,
            "ran_scan": False,
            "sync_window_active": self._is_sync_window_active(current_time),
            "alert_window_active": self._is_alert_window_active(current_time),
            "scan_interval_minutes": self.config.scan_interval_minutes,
        }
        if payload["sync_window_active"]:
            payload["sync"] = self.run_sync(now=current_time)
            payload["ran_sync"] = True
        if payload["alert_window_active"]:
            payload["scan"] = self.run_scan(
                account_size=account_size,
                persist_ideas=persist_ideas,
                post_webhook_flag=post_webhook_flag,
                source_room=source_room,
                allow_outside_window=False,
                now=current_time,
            )
            payload["ran_scan"] = True
        return payload

    def get_sync_status(self, *, symbol: str | None = None, now: datetime | None = None) -> dict[str, object]:
        watchlist = [symbol] if symbol else list(self.config.twelvedata_symbols)
        current_time = self._now(now)
        state = get_state(self.connection, _sync_key(symbol))
        if state is None:
            symbols = {
                item: {
                    "category": live_symbol_profile(item).category,
                    "interval": self._preferred_cached_interval(item),
                    "latest_cached_timestamp": self._latest_cached_timestamp(item, self._preferred_cached_interval(item)),
                }
                for item in watchlist
            }
            state = {
                "provider": "twelvedata",
                "watchlist": watchlist,
                "primary_symbol": symbol or self.config.primary_symbol,
                "backfill_days": self.config.backfill_days,
                "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
                "last_sync_time": None,
                "last_sync_summary": None,
                "symbols": symbols,
            }
        status = {
            **state,
            "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
        }
        status["text"] = render_sync_status(status)
        return status

    def run_scan(
        self,
        *,
        account_size: float = 10_000,
        persist_ideas: bool = False,
        post_webhook_flag: bool = False,
        source_room: str | None = None,
        allow_outside_window: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current_time = self._now(now)
        alert_window_active = self._is_alert_window_active(current_time)
        manual_override = (
            allow_outside_window
            if allow_outside_window is not None
            else self.config.allow_outside_window_manual_scan
        )
        may_alert = alert_window_active or manual_override
        existing_ids = {idea.idea_id for idea in list_trade_ideas(self.connection, limit=1000)}
        symbol_payloads: dict[str, dict[str, object]] = {}
        all_new_ideas = []
        detected_count = 0
        any_cached = False
        for symbol in self.config.twelvedata_symbols:
            interval = self._preferred_cached_interval(symbol)
            if interval is None:
                symbol_payloads[symbol] = {
                    "category": live_symbol_profile(symbol).category,
                    "interval": None,
                    "latest_cached_timestamp": None,
                    "bars_used": 0,
                    "valid_setups": 0,
                    "rejected_setups": 0,
                    "persisted_ideas": 0,
                    "new_idea_ids": [],
                    "alerted_idea_ids": [],
                    "error": "no cached live bars are available yet; run /sync/run first",
                }
                continue
            bars = fetch_recent_market_bars(self.connection, symbol=symbol, interval=interval, limit=_scan_limit(interval))
            if not bars:
                symbol_payloads[symbol] = {
                    "category": live_symbol_profile(symbol).category,
                    "interval": interval,
                    "latest_cached_timestamp": self._latest_cached_timestamp(symbol, interval),
                    "bars_used": 0,
                    "valid_setups": 0,
                    "rejected_setups": 0,
                    "persisted_ideas": 0,
                    "new_idea_ids": [],
                    "alerted_idea_ids": [],
                    "error": "no cached live bars are available yet; run /sync/run first",
                }
                continue
            any_cached = True
            provider = _SingleSnapshotProvider(_snapshot_from_bars(symbol, bars))
            plan = build_trade_plan(provider, account_size, symbols=[symbol], source_room=source_room or self.config.room_label)
            detected_count += len(plan.setups)
            persisted_ideas = (
                [create_trade_idea(self.connection, source_room=plan.source_room, setup=setup) for setup in plan.setups]
                if persist_ideas
                else []
            )
            new_ideas = [idea for idea in persisted_ideas if idea.idea_id not in existing_ids]
            existing_ids.update(idea.idea_id for idea in new_ideas)
            all_new_ideas.extend(new_ideas)
            symbol_payloads[symbol] = {
                "category": live_symbol_profile(symbol).category,
                "interval": interval,
                "latest_cached_timestamp": self._latest_cached_timestamp(symbol, interval),
                "bars_used": len(bars),
                "valid_setups": len(plan.setups),
                "rejected_setups": len(plan.rejected_setups),
                "persisted_ideas": len(new_ideas),
                "new_idea_ids": [idea.idea_id for idea in new_ideas],
                "alerted_idea_ids": [],
                "plan": plan_contract(plan),
            }

        if not any_cached:
            raise ValueError("no cached live bars are available yet; run /sync/run first")

        webhook_payload = None
        if post_webhook_flag:
            if may_alert and all_new_ideas:
                webhook_payload = post_message(self.config, render_webhook_scan(all_new_ideas))
            elif may_alert:
                webhook_payload = suppressed_result(
                    config=self.config,
                    reason_code="no_new_alerts",
                    reason="alert suppressed by policy: no new ideas qualified for notification",
                )
            else:
                webhook_payload = suppressed_result(
                    config=self.config,
                    reason_code="alert_suppressed_policy",
                    reason="alert suppressed by policy: outside alert window",
                )
            if all_new_ideas and webhook_payload is not None:
                updated = record_alert_state(
                    self.connection,
                    [idea.idea_id for idea in all_new_ideas],
                    result=webhook_payload,
                    alert_channel=source_room or self.config.room_label,
                    attempted_at=current_time.isoformat(),
                )
                updated_map = {idea.idea_id: idea for idea in updated}
                for symbol, details in symbol_payloads.items():
                    details["alerted_idea_ids"] = [
                        idea_id
                        for idea_id in details["new_idea_ids"]
                        if updated_map.get(idea_id) is not None and updated_map[idea_id].alert_sent
                    ]

        persisted_count = len(all_new_ideas)
        refreshed_ideas = []
        alerted_count = 0
        if all_new_ideas:
            refreshed_ideas = [get_trade_idea(self.connection, idea.idea_id) for idea in all_new_ideas]
            refreshed_map = {idea.idea_id: idea for idea in refreshed_ideas}
            alerted_count = sum(
                1
                for idea in all_new_ideas
                if refreshed_map.get(idea.idea_id) is not None and refreshed_map[idea.idea_id].alert_sent
            )
        alert_failures = persisted_count - alerted_count if webhook_payload and not webhook_payload.get("sent") else 0

        summary = {
            "watchlist": list(self.config.twelvedata_symbols),
            "alert_window_active": alert_window_active,
            "manual_override_used": bool(not alert_window_active and manual_override),
            "detected_ideas": detected_count,
            "persisted_ideas": persisted_count,
            "alerted_ideas": alerted_count,
            "alert_failures": alert_failures,
            "alert_reason": webhook_payload.get("reason") if webhook_payload else None,
            "symbols": {
                symbol: {
                    "bars_used": details["bars_used"],
                    "valid_setups": details["valid_setups"],
                    "persisted_ideas": details["persisted_ideas"],
                    "alerted_ideas": len(details["alerted_idea_ids"]),
                    "new_idea_ids": details["new_idea_ids"],
                    **({"error": details["error"]} if "error" in details else {}),
                }
                for symbol, details in symbol_payloads.items()
            },
        }
        payload = {
            "watchlist": list(self.config.twelvedata_symbols),
            "primary_symbol": self.config.primary_symbol,
            "symbols": symbol_payloads,
            "detected": detected_count,
            "persisted": bool(all_new_ideas),
            "persisted_ideas": persisted_count,
            "alerted_ideas": alerted_count,
            "alert_failures": alert_failures,
            "idea_ids": [idea.idea_id for idea in all_new_ideas],
            "ideas": [idea_contract(item) for item in refreshed_ideas],
            "alert_window": self._window_payload(self.config.alert_start, self.config.alert_end, current_time),
            "alert_window_active": alert_window_active,
            "manual_override_used": bool(not alert_window_active and manual_override),
            "last_scan_time": current_time.isoformat(),
            "last_scan_result_summary": summary,
            "text": render_window_state(
                alert_window_active=alert_window_active,
                manual_override=bool(not alert_window_active and manual_override),
                persist_requested=persist_ideas,
                webhook_requested=post_webhook_flag,
            ),
        }
        set_state(
            self.connection,
            _scan_key(None),
            {
                "watchlist": list(self.config.twelvedata_symbols),
                "primary_symbol": self.config.primary_symbol,
                "last_scan_time": current_time.isoformat(),
                "last_scan_result_summary": summary,
                "symbols": {
                    symbol: {
                        "category": details["category"],
                        "interval": details["interval"],
                        "latest_cached_timestamp": details.get("latest_cached_timestamp"),
                        "last_scan_summary": {
                            "bars_used": details["bars_used"],
                            "valid_setups": details["valid_setups"],
                            "rejected_setups": details["rejected_setups"],
                            "persisted_ideas": details["persisted_ideas"],
                            "alerted_ideas": len(details["alerted_idea_ids"]),
                            "new_idea_ids": details["new_idea_ids"],
                            **({"error": details["error"]} if "error" in details else {}),
                        },
                    }
                    for symbol, details in symbol_payloads.items()
                },
            },
        )
        if webhook_payload is not None:
            payload["webhook"] = webhook_payload
        payload["text"] = "\n\n".join([payload["text"], render_scan_status(self.get_scan_status(now=current_time))])
        return payload

    def get_scan_status(self, *, symbol: str | None = None, now: datetime | None = None) -> dict[str, object]:
        watchlist = [symbol] if symbol else list(self.config.twelvedata_symbols)
        current_time = self._now(now)
        state = get_state(self.connection, _scan_key(symbol))
        if state is None:
            state = {
                "watchlist": watchlist,
                "primary_symbol": symbol or self.config.primary_symbol,
                "last_scan_time": None,
                "last_scan_result_summary": None,
                "symbols": {
                    item: {
                        "category": live_symbol_profile(item).category,
                        "interval": self._preferred_cached_interval(item),
                        "latest_cached_timestamp": self._latest_cached_timestamp(item, self._preferred_cached_interval(item)),
                        "last_scan_summary": None,
                    }
                    for item in watchlist
                },
            }
        status = {
            **state,
            "alert_window": self._window_payload(self.config.alert_start, self.config.alert_end, current_time),
            "active": self._is_alert_window_active(current_time),
        }
        status["text"] = render_scan_status(status)
        return status

    def _preferred_cached_interval(self, symbol: str) -> str | None:
        intervals = list_cached_intervals(self.connection, symbol=symbol)
        if "1min" in intervals:
            return "1min"
        if "5min" in intervals:
            return "5min"
        return None

    def _latest_cached_timestamp(self, symbol: str, interval: str | None) -> str | None:
        if not interval:
            return None
        return get_latest_cached_timestamp(self.connection, symbol=symbol, interval=interval)

    def _window_payload(self, start: str, end: str, now: datetime) -> dict[str, object]:
        return {
            "start": start,
            "end": end,
            "active": _time_in_window(now, start, end),
            "now": now.strftime("%H:%M"),
        }

    def _is_sync_window_active(self, now: datetime) -> bool:
        return _time_in_window(now, self.config.sync_start, self.config.sync_end)

    def _is_alert_window_active(self, now: datetime) -> bool:
        return _time_in_window(now, self.config.alert_start, self.config.alert_end)

    def _now(self, value: datetime | None) -> datetime:
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=NEW_YORK)
            return value.astimezone(NEW_YORK)
        return datetime.now(UTC).astimezone(NEW_YORK)


class _SingleSnapshotProvider(MarketDataProvider):
    def __init__(self, snapshot: MarketSnapshot):
        self.snapshot = snapshot

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        if symbol.upper() != self.snapshot.symbol:
            raise ValueError(f"unsupported live scan symbol={symbol!r}")
        return self.snapshot


def _snapshot_from_bars(symbol: str, bars: list) -> MarketSnapshot:
    return build_live_snapshot(symbol, bars)


def _time_in_window(now: datetime, start: str, end: str) -> bool:
    current = now.strftime("%H:%M")
    return start <= current <= end


def _scan_limit(interval: str) -> int:
    return 4000 if interval == "1min" else 1500


def _preferred_intervals(active_interval: str) -> tuple[str, ...]:
    if active_interval == "5min":
        return ("5min", "1min")
    return ("1min", "5min")


def _sync_key(symbol: str | None) -> str:
    return f"sync_status:{symbol}" if symbol else "sync_status:watchlist"


def _scan_key(symbol: str | None) -> str:
    return f"scan_status:{symbol}" if symbol else "scan_status:watchlist"
