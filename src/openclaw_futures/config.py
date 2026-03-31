"""Static configuration for openclaw-futures."""
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
DATA_DIR = Path(os.getenv("OPENCLAW_DATA_DIR", DEFAULT_DATA_DIR))
DEFAULT_PROVIDER = os.getenv("OPENCLAW_DEFAULT_PROVIDER", "file")

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
MAX_DISCORD_MESSAGE_LEN = 1900
