"""Package-local configuration for TradingClaw Futures."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ContractSpec:
    symbol: str
    tick_size: float
    tick_value: float
    price_decimals: int
    entry_buffer_ticks: int
    min_stop_ticks: int
    atr_threshold_ticks: int
    atr_multiplier: float


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PACKAGE_ROOT / "data" / "fixtures"
DEFAULT_DB_PATH = PACKAGE_ROOT / "data" / "runtime" / "tradingclaw.sqlite3"

CONTRACT_SPECS: dict[str, ContractSpec] = {
    "MCL": ContractSpec(
        symbol="MCL",
        tick_size=0.01,
        tick_value=1.00,
        price_decimals=2,
        entry_buffer_ticks=3,
        min_stop_ticks=15,
        atr_threshold_ticks=10,
        atr_multiplier=1.25,
    ),
    "M6E": ContractSpec(
        symbol="M6E",
        tick_size=0.00005,
        tick_value=0.625,
        price_decimals=5,
        entry_buffer_ticks=2,
        min_stop_ticks=16,
        atr_threshold_ticks=10,
        atr_multiplier=1.25,
    ),
}

DEFAULT_SYMBOLS = ("MCL", "M6E")


@dataclass(frozen=True, slots=True)
class AppConfig:
    host: str
    port: int
    data_dir: Path
    default_provider: str
    db_path: Path
    webhook_url: str
    webhook_thread_id: str
    room_label: str
    log_level: str
    twelvedata_api_key: str
    twelvedata_base_url: str
    backfill_days: int
    sync_start: str
    sync_end: str
    alert_start: str
    alert_end: str
    scan_interval_minutes: int
    allow_outside_window_manual_scan: bool
    live_symbol: str
    live_symbol_map: dict[str, str]

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            host=os.getenv("TRADINGCLAW_HOST", "127.0.0.1"),
            port=int(os.getenv("TRADINGCLAW_PORT", "8787")),
            data_dir=Path(os.getenv("TRADINGCLAW_DATA_DIR", str(DEFAULT_DATA_DIR))),
            default_provider=os.getenv("TRADINGCLAW_DEFAULT_PROVIDER", "file"),
            db_path=Path(os.getenv("TRADINGCLAW_DB_PATH", str(DEFAULT_DB_PATH))),
            webhook_url=os.getenv("TRADINGCLAW_WEBHOOK_URL", ""),
            webhook_thread_id=os.getenv("TRADINGCLAW_WEBHOOK_THREAD_ID", ""),
            room_label=os.getenv("TRADINGCLAW_ROOM_LABEL", "trading-room"),
            log_level=os.getenv("TRADINGCLAW_LOG_LEVEL", "INFO").upper(),
            twelvedata_api_key=os.getenv("TRADINGCLAW_TWELVEDATA_API_KEY", ""),
            twelvedata_base_url=os.getenv("TRADINGCLAW_TWELVEDATA_BASE_URL", "https://api.twelvedata.com"),
            backfill_days=int(os.getenv("TRADINGCLAW_BACKFILL_DAYS", "10")),
            sync_start=os.getenv("TRADINGCLAW_SYNC_START", "08:00"),
            sync_end=os.getenv("TRADINGCLAW_SYNC_END", "13:00"),
            alert_start=os.getenv("TRADINGCLAW_ALERT_START", "08:30"),
            alert_end=os.getenv("TRADINGCLAW_ALERT_END", "11:30"),
            scan_interval_minutes=int(os.getenv("TRADINGCLAW_SCAN_INTERVAL_MINUTES", "5")),
            allow_outside_window_manual_scan=_env_bool(
                os.getenv("TRADINGCLAW_ALLOW_OUTSIDE_WINDOW_MANUAL_SCAN", "true")
            ),
            live_symbol=os.getenv("TRADINGCLAW_LIVE_SYMBOL", "M6E").upper(),
            live_symbol_map={
                "M6E": os.getenv("TRADINGCLAW_TWELVEDATA_M6E_SYMBOL", "EUR/USD"),
            },
        )

    def sync_start_time(self) -> time:
        return parse_clock(self.sync_start)

    def sync_end_time(self) -> time:
        return parse_clock(self.sync_end)

    def alert_start_time(self) -> time:
        return parse_clock(self.alert_start)

    def alert_end_time(self) -> time:
        return parse_clock(self.alert_end)


def parse_clock(value: str) -> time:
    hour_text, minute_text = value.split(":", 1)
    return time(hour=int(hour_text), minute=int(minute_text))


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
