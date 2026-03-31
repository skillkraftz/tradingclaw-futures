"""Render snapshots, setups, and account plans for Discord."""
from __future__ import annotations

from openclaw_futures.config import CONTRACT_SPECS, MAX_DISCORD_MESSAGE_LEN
from openclaw_futures.models import AccountPlan, MarketSnapshot, SetupCandidate, TradePlan


def render_trades(account_plan: AccountPlan) -> str:
    lines = ["**Trade Allocation**"]
    for allocation in account_plan.allocations:
        lines.append(
            f"{allocation.label.title()}: {allocation.total_contracts} total "
            f"(MCL {allocation.mcl_contracts} / M6E {allocation.m6e_contracts}) "
            f"| risk ${allocation.estimated_risk:.2f} | reward ${allocation.estimated_reward:.2f}"
        )
    return _cap("\n".join(lines))


def render_setups(setups: list[SetupCandidate], symbol: str | None = None) -> str:
    title = f"**Best Setups: {symbol}**" if symbol else "**Best Setups**"
    lines = [title]
    if not setups:
        lines.append("No valid 1:3 setups found.")
        return _cap("\n".join(lines))
    for setup in setups:
        lines.append(_format_setup(setup))
    return _cap("\n".join(lines))


def render_levels(snapshots: list[MarketSnapshot]) -> str:
    lines = ["**Key Levels**"]
    for snapshot in snapshots:
        spec = CONTRACT_SPECS[snapshot.symbol]
        lines.append(
            f"{snapshot.symbol}: O/N {fmt_price(snapshot.overnight_low, spec.price_decimals)}-"
            f"{fmt_price(snapshot.overnight_high, spec.price_decimals)} | "
            f"PD {fmt_price(snapshot.prior_day_low, spec.price_decimals)}-"
            f"{fmt_price(snapshot.prior_day_high, spec.price_decimals)} | "
            f"invalidation {fmt_price(snapshot.invalidation_low, spec.price_decimals)}-"
            f"{fmt_price(snapshot.invalidation_high, spec.price_decimals)}"
        )
    return _cap("\n".join(lines))


def render_account(account_plan: AccountPlan) -> str:
    lines = [
        "**Account Plan**",
        f"Account size: ${account_plan.account_size:.2f}",
        f"Risk budget: {account_plan.risk_percent:.2f}% (${account_plan.risk_budget:.2f})",
        f"Daily loss cap: ${account_plan.daily_loss_cap:.2f}",
        f"Max open risk: ${account_plan.max_open_risk:.2f}",
    ]
    return _cap("\n".join(lines))


def render_plan(trade_plan: TradePlan) -> str:
    lines = [
        "**OpenClaw Futures Plan**",
        render_account(trade_plan.account_plan).replace("**Account Plan**\n", ""),
        "",
        "Best setups:",
    ]
    valid_setups = [setup for setup in trade_plan.setups if setup.valid]
    if valid_setups:
        for setup in valid_setups[:4]:
            lines.append(_format_setup(setup))
    else:
        lines.append("No valid 1:3 setups available.")

    lines.append("")
    lines.append("Contract split:")
    for allocation in trade_plan.account_plan.allocations:
        lines.append(
            f"{allocation.label.title()}: MCL {allocation.mcl_contracts}, M6E {allocation.m6e_contracts}, "
            f"risk ${allocation.estimated_risk:.2f}, reward ${allocation.estimated_reward:.2f}"
        )

    lines.append("")
    lines.append("Do-not-trade conditions:")
    for condition in trade_plan.do_not_trade_conditions:
        lines.append(f"- {condition}")
    return _cap("\n".join(lines))


def fmt_price(value: float | None, decimals: int) -> str:
    if value is None:
        return "?"
    return f"{value:.{decimals}f}"


def _format_setup(setup: SetupCandidate) -> str:
    spec = CONTRACT_SPECS[setup.symbol]
    entry = f"{fmt_price(setup.entry_min, spec.price_decimals)}-{fmt_price(setup.entry_max, spec.price_decimals)}"
    return (
        f"{setup.symbol} {setup.bias} {setup.setup_type} | "
        f"entry {entry} | stop {fmt_price(setup.stop, spec.price_decimals)} | "
        f"target {fmt_price(setup.target, spec.price_decimals)} | "
        f"risk ${setup.risk_per_contract:.2f} | reward ${setup.reward_per_contract:.2f} | "
        f"RR {setup.rr:.2f} | score {setup.score}"
    )


def _cap(message: str) -> str:
    if len(message) <= MAX_DISCORD_MESSAGE_LEN:
        return message
    return message[: MAX_DISCORD_MESSAGE_LEN - 1] + "…"
