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
class MarketBar:
    symbol: str
    interval: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = ""


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
class RejectedSetup:
    symbol: str
    bias: str
    setup_type: str
    rejection_reasons: list[str]
    entry_min: float | None = None
    entry_max: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    confidence: float = 0.0
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
    rejection_reasons: list[str] = field(default_factory=list)


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
    rejected_setups: list[RejectedSetup]
    do_not_trade_conditions: list[str]
    level_summary: dict[str, MarketSnapshot]
    source_room: str


@dataclass(frozen=True, slots=True)
class TradeIdea:
    idea_id: int
    created_at: str
    source_room: str
    symbol: str
    setup_type: str
    bias: str
    entry_min: float
    entry_max: float
    stop: float
    target: float
    risk_per_contract: float
    reward_per_contract: float
    rr: float
    confidence: float
    notes_json: dict[str, object]
    status: str


@dataclass(frozen=True, slots=True)
class TradeAction:
    action_id: int
    idea_id: int
    acted_at: str
    action_type: str
    contracts: int | None = None
    entry_fill: float | None = None
    exit_fill: float | None = None
    pnl_dollars: float | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class StatsSummary:
    total_ideas: int
    proposed: int
    taken: int
    skipped: int
    invalidated: int
    wins: int
    losses: int
    breakeven: int
    realized_pnl: float
    average_pnl: float


IDEA_STATUS_PROPOSED = "proposed"
IDEA_STATUS_TAKEN = "taken"
IDEA_STATUS_SKIPPED = "skipped"
IDEA_STATUS_INVALIDATED = "invalidated"
IDEA_STATUS_WIN = "win"
IDEA_STATUS_LOSS = "loss"
IDEA_STATUS_BREAKEVEN = "breakeven"
