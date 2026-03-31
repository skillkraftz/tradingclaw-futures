"""Cached live-data sync and scan service."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from openclaw_futures.analysis.m6e_levels import build_m6e_snapshot
from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_contracts import build_trade_plan, idea_contract, plan_contract
from openclaw_futures.integrations.webhook import post_message
from openclaw_futures.models import MarketBar, MarketSnapshot
from openclaw_futures.providers.base import MarketDataProvider
from openclaw_futures.providers.twelvedata_provider import TwelveDataProvider
from openclaw_futures.render.text_render import (
    render_scan_status,
    render_sync_status,
    render_window_state,
)
from openclaw_futures.render.webhook_render import render_webhook_plan
from openclaw_futures.storage.ideas import create_trade_idea
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
        live_symbol = (symbol_override or self.config.live_symbol).upper()
        current_time = self._now(now)
        backfill_days = days or self.config.backfill_days
        prior_status = self.get_sync_status(symbol=live_symbol, now=current_time)
        active_interval = interval_override or prior_status.get("interval") or self._preferred_cached_interval(live_symbol)
        if force_full_backfill or active_interval is None or needs_initial_backfill(self.connection, symbol=live_symbol, interval=active_interval):
            start_at = (current_time - timedelta(days=backfill_days)).strftime("%Y-%m-%d %H:%M:%S")
            interval, bars, provider_symbol = self.live_provider.fetch_preferred_bars(
                symbol=live_symbol,
                start_at=start_at,
                interval_override=interval_override,
            )
            sync_mode = "backfill"
        else:
            latest = get_latest_cached_timestamp(self.connection, symbol=live_symbol, interval=active_interval)
            interval, bars, provider_symbol = self.live_provider.fetch_preferred_bars(
                symbol=live_symbol,
                start_at=latest,
                interval_override=interval_override,
                preferred_intervals=_preferred_intervals(active_interval),
            )
            sync_mode = "incremental"

        inserted = insert_market_bars(
            self.connection,
            [
                MarketBar(
                    symbol=live_symbol,
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
        latest_cached_timestamp = get_latest_cached_timestamp(self.connection, symbol=live_symbol, interval=interval)
        summary = {
            "provider": "twelvedata",
            "provider_symbol": provider_symbol,
            "symbol": live_symbol,
            "interval": interval,
            "backfill_days": backfill_days,
            "sync_mode": sync_mode,
            "fetched_bars": len(bars),
            "stored_changes": inserted,
            "latest_cached_timestamp": latest_cached_timestamp,
            "window_active": self._is_sync_window_active(current_time),
        }
        payload = {
            "provider": "twelvedata",
            "symbol": live_symbol,
            "interval": interval,
            "backfill_days": backfill_days,
            "latest_cached_timestamp": latest_cached_timestamp,
            "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
            "last_sync_time": current_time.isoformat(),
            "last_sync_summary": summary,
            "text": render_sync_status(
                {
                    "provider": "twelvedata",
                    "symbol": live_symbol,
                    "interval": interval,
                    "backfill_days": backfill_days,
                    "latest_cached_timestamp": latest_cached_timestamp,
                    "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
                    "last_sync_time": current_time.isoformat(),
                    "last_sync_summary": summary,
                }
            ),
        }
        set_state(self.connection, _sync_key(live_symbol), payload)
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
        live_symbol = (symbol or self.config.live_symbol).upper()
        current_time = self._now(now)
        state = get_state(self.connection, _sync_key(live_symbol)) or {}
        status = {
            "provider": "twelvedata",
            "symbol": live_symbol,
            "interval": state.get("interval") or self._preferred_cached_interval(live_symbol),
            "backfill_days": state.get("backfill_days", self.config.backfill_days),
            "latest_cached_timestamp": state.get("latest_cached_timestamp")
            or self._latest_cached_timestamp(live_symbol, state.get("interval")),
            "sync_window": self._window_payload(self.config.sync_start, self.config.sync_end, current_time),
            "last_sync_time": state.get("last_sync_time"),
            "last_sync_summary": state.get("last_sync_summary"),
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
        live_symbol = self.config.live_symbol
        interval = self._preferred_cached_interval(live_symbol)
        if interval is None:
            raise ValueError("no cached live bars are available yet; run /sync/run first")
        bars = fetch_recent_market_bars(self.connection, symbol=live_symbol, interval=interval, limit=_scan_limit(interval))
        if not bars:
            raise ValueError("no cached live bars are available yet; run /sync/run first")

        provider = _SingleSnapshotProvider(_snapshot_from_bars(live_symbol, bars))
        plan = build_trade_plan(provider, account_size, symbols=[live_symbol], source_room=source_room or self.config.room_label)

        alert_window_active = self._is_alert_window_active(current_time)
        manual_override = (
            allow_outside_window
            if allow_outside_window is not None
            else self.config.allow_outside_window_manual_scan
        )
        may_alert = alert_window_active or manual_override
        persisted_ideas = [create_trade_idea(self.connection, source_room=plan.source_room, setup=setup) for setup in plan.setups] if persist_ideas and may_alert else []
        webhook_payload = None
        if post_webhook_flag:
            if may_alert:
                webhook_payload = post_message(self.config, render_webhook_plan(plan))
            else:
                webhook_payload = {
                    "enabled": bool(self.config.webhook_url),
                    "sent": False,
                    "reason": "outside alert window",
                }

        summary = {
            "symbol": live_symbol,
            "interval": interval,
            "bars_used": len(bars),
            "valid_setups": len(plan.setups),
            "rejected_setups": len(plan.rejected_setups),
            "alert_window_active": alert_window_active,
            "manual_override_used": bool(not alert_window_active and manual_override),
            "persisted_idea_ids": [idea.idea_id for idea in persisted_ideas],
            "webhook_sent": bool(webhook_payload and webhook_payload.get("sent")),
        }
        payload = {
            "plan": plan_contract(plan),
            "persisted": bool(persist_ideas and may_alert),
            "idea_ids": [idea.idea_id for idea in persisted_ideas],
            "ideas": [idea_contract(idea) for idea in persisted_ideas],
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
        if webhook_payload is not None:
            payload["webhook"] = webhook_payload
        set_state(
            self.connection,
            _scan_key(live_symbol),
            {
                "symbol": live_symbol,
                "interval": interval,
                "last_scan_time": current_time.isoformat(),
                "last_scan_result_summary": summary,
            },
        )
        payload["text"] = "\n\n".join([payload["text"], render_scan_status(self.get_scan_status(symbol=live_symbol, now=current_time))])
        return payload

    def get_scan_status(self, *, symbol: str | None = None, now: datetime | None = None) -> dict[str, object]:
        live_symbol = (symbol or self.config.live_symbol).upper()
        current_time = self._now(now)
        state = get_state(self.connection, _scan_key(live_symbol)) or {}
        status = {
            "symbol": live_symbol,
            "interval": state.get("interval") or self._preferred_cached_interval(live_symbol),
            "alert_window": self._window_payload(self.config.alert_start, self.config.alert_end, current_time),
            "active": self._is_alert_window_active(current_time),
            "last_scan_time": state.get("last_scan_time"),
            "last_scan_result_summary": state.get("last_scan_result_summary"),
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
    if symbol != "M6E":
        raise ValueError("live cached-bar scanning is currently supported for M6E only")
    return build_m6e_snapshot(bars)


def _time_in_window(now: datetime, start: str, end: str) -> bool:
    current = now.strftime("%H:%M")
    return start <= current <= end


def _scan_limit(interval: str) -> int:
    return 4000 if interval == "1min" else 1500


def _preferred_intervals(active_interval: str) -> tuple[str, ...]:
    if active_interval == "5min":
        return ("5min", "1min")
    return ("1min", "5min")


def _sync_key(symbol: str) -> str:
    return f"sync_status:{symbol}"


def _scan_key(symbol: str) -> str:
    return f"scan_status:{symbol}"
