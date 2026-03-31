"""Structured contracts for external orchestration layers such as OpenClaw."""
from __future__ import annotations

from dataclasses import asdict

from openclaw_futures.analysis.setups import evaluate_setups
from openclaw_futures.config import CONTRACT_SPECS, DEFAULT_SYMBOLS
from openclaw_futures.models import AccountPlan, MarketSnapshot, RejectedSetup, SetupCandidate, StatsSummary, TradeIdea, TradePlan
from openclaw_futures.providers.base import MarketDataProvider
from openclaw_futures.risk.account_plan import build_account_plan


def normalize_symbols(symbols: list[str] | None) -> list[str]:
    requested = symbols or list(DEFAULT_SYMBOLS)
    normalized: list[str] = []
    for symbol in requested:
        name = symbol.upper()
        if name not in CONTRACT_SPECS:
            raise ValueError(f"unsupported symbol={name!r}")
        normalized.append(name)
    return normalized


def load_snapshots(provider: MarketDataProvider, symbols: list[str] | None = None) -> list[MarketSnapshot]:
    return [provider.get_snapshot(symbol) for symbol in normalize_symbols(symbols)]


def build_trade_plan(
    provider: MarketDataProvider,
    account_size: float,
    symbols: list[str] | None = None,
    source_room: str = "trading-room",
) -> TradePlan:
    snapshots = load_snapshots(provider, symbols)
    setups: list[SetupCandidate] = []
    rejected_setups: list[RejectedSetup] = []
    for snapshot in snapshots:
        valid, rejected = evaluate_setups(snapshot)
        setups.extend(valid)
        rejected_setups.extend(rejected)
    account_plan = build_account_plan(account_size, setups)
    return TradePlan(
        account_plan=account_plan,
        setups=sorted(setups, key=lambda item: (item.score, item.rr, item.confidence), reverse=True),
        rejected_setups=sorted(rejected_setups, key=lambda item: (item.symbol, item.bias)),
        do_not_trade_conditions=do_not_trade_conditions(snapshots, setups, rejected_setups),
        level_summary={snapshot.symbol: snapshot for snapshot in snapshots},
        source_room=source_room,
    )


def do_not_trade_conditions(
    snapshots: list[MarketSnapshot],
    setups: list[SetupCandidate],
    rejected_setups: list[RejectedSetup],
) -> list[str]:
    conditions: list[str] = []
    for snapshot in snapshots:
        if snapshot.atr is None:
            conditions.append(f"{snapshot.symbol}: ATR unavailable.")
        if snapshot.overnight_high is None or snapshot.overnight_low is None:
            conditions.append(f"{snapshot.symbol}: overnight range unavailable.")
        if snapshot.invalidation_high is not None and snapshot.last_price is not None and snapshot.last_price > snapshot.invalidation_high:
            conditions.append(f"{snapshot.symbol}: price is above invalidation high.")
        if snapshot.invalidation_low is not None and snapshot.last_price is not None and snapshot.last_price < snapshot.invalidation_low:
            conditions.append(f"{snapshot.symbol}: price is below invalidation low.")
    if not setups:
        conditions.append("No valid explicit 1:3 setups are available.")
    if rejected_setups:
        conditions.append("Rejected setups remain informational only and must not be executed.")
    conditions.append("Stand aside after hitting the daily loss cap.")
    conditions.append("Do not chase entries outside the defined entry bands.")
    return conditions


def setup_contract(setup: SetupCandidate) -> dict[str, object]:
    return asdict(setup)


def rejected_setup_contract(setup: RejectedSetup) -> dict[str, object]:
    return asdict(setup)


def snapshot_contract(snapshot: MarketSnapshot) -> dict[str, object]:
    payload = asdict(snapshot)
    payload["bars"] = [asdict(bar) for bar in snapshot.bars[-5:]]
    return payload


def account_contract(account_plan: AccountPlan) -> dict[str, object]:
    return asdict(account_plan)


def idea_contract(idea: TradeIdea) -> dict[str, object]:
    return asdict(idea)


def stats_contract(stats: StatsSummary) -> dict[str, object]:
    return asdict(stats)


def plan_contract(plan: TradePlan) -> dict[str, object]:
    return {
        "source_room": plan.source_room,
        "account_plan": account_contract(plan.account_plan),
        "valid_setups": [setup_contract(item) for item in plan.setups],
        "rejected_setups": [rejected_setup_contract(item) for item in plan.rejected_setups],
        "do_not_trade_conditions": list(plan.do_not_trade_conditions),
        "levels": {symbol: snapshot_contract(snapshot) for symbol, snapshot in plan.level_summary.items()},
    }


def reasoning_context_contract(
    plan: TradePlan,
    requested_symbols: list[str],
    stats: StatsSummary | None = None,
    recent_ideas: list[TradeIdea] | None = None,
) -> dict[str, object]:
    return {
        "account_size": plan.account_plan.account_size,
        "requested_symbols": requested_symbols,
        "valid_setups": [setup_contract(item) for item in plan.setups],
        "rejected_setups": [rejected_setup_contract(item) for item in plan.rejected_setups],
        "major_levels": {
            symbol: {
                "overnight_high": snapshot.overnight_high,
                "overnight_low": snapshot.overnight_low,
                "prior_day_high": snapshot.prior_day_high,
                "prior_day_low": snapshot.prior_day_low,
                "daily_open": snapshot.daily_open,
                "last_price": snapshot.last_price,
            }
            for symbol, snapshot in plan.level_summary.items()
        },
        "invalidation_zones": {
            symbol: {
                "invalidation_low": snapshot.invalidation_low,
                "invalidation_high": snapshot.invalidation_high,
            }
            for symbol, snapshot in plan.level_summary.items()
        },
        "do_not_trade_conditions": list(plan.do_not_trade_conditions),
        "contract_sizing_summary": account_contract(plan.account_plan),
        "journal_status_summary": {
            "stats": stats_contract(stats) if stats else None,
            "recent_ideas": [idea_contract(item) for item in recent_ideas or []],
        },
    }
