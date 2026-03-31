"""Package-local configuration for TradingClaw Futures."""
from __future__ import annotations

import os
from dataclasses import dataclass
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
        )
