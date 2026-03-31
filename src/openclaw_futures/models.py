"""Typed models used across the package."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Bar:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    bars: list[Bar]
    overnight_high: float | None
    overnight_low: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    daily_open: float | None
    last_price: float | None
    atr: float | None
    invalidation_high: float | None = None
    invalidation_low: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SetupCandidate:
    symbol: str
    bias: str
    entry_min: float
    entry_max: float
    stop: float
    target: float
    risk_per_contract: float
    reward_per_contract: float
    rr: float
    confidence: float
    setup_type: str
    notes: list[str]
    valid: bool
    score: int


@dataclass(frozen=True, slots=True)
class ContractAllocation:
    label: str
    total_contracts: int
    mcl_contracts: int
    m6e_contracts: int
    estimated_risk: float
    estimated_reward: float


@dataclass(frozen=True, slots=True)
class AccountPlan:
    account_size: float
    risk_percent: float
    risk_budget: float
    daily_loss_cap: float
    max_open_risk: float
    allocations: list[ContractAllocation]
    notes: list[str]


@dataclass(frozen=True, slots=True)
class TradePlan:
    account_plan: AccountPlan
    setups: list[SetupCandidate]
    do_not_trade_conditions: list[str]
    level_summary: dict[str, MarketSnapshot]
