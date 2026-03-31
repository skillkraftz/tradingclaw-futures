"""Webhook rendering helpers."""
from __future__ import annotations

from openclaw_futures.models import TradeAction, TradeIdea, TradePlan


def render_webhook_plan(plan: TradePlan) -> str:
    lines = [f"TradingClaw plan for {plan.source_room}"]
    for setup in plan.setups:
        lines.append(
            f"{setup.symbol} {setup.bias} entry {setup.entry_min}-{setup.entry_max} stop {setup.stop} target {setup.target} RR {setup.rr:.2f}"
        )
    if not plan.setups:
        lines.append("No valid setups.")
    return "\n".join(lines)


def render_webhook_idea(idea: TradeIdea) -> str:
    return (
        f"TradingClaw idea {idea.idea_id} | {idea.symbol} {idea.bias} "
        f"| entry {idea.entry_min}-{idea.entry_max} | stop {idea.stop} | target {idea.target} "
        f"| RR {idea.rr:.2f} | status {idea.status}"
    )


def render_webhook_transition(idea: TradeIdea, action: TradeAction) -> str:
    parts = [
        f"TradingClaw update | idea {idea.idea_id}",
        f"{idea.symbol} {idea.bias}",
        f"status {idea.status}",
        f"action {action.action_type}",
    ]
    if action.contracts is not None:
        parts.append(f"contracts {action.contracts}")
    if action.entry_fill is not None:
        parts.append(f"entry {action.entry_fill}")
    if action.exit_fill is not None:
        parts.append(f"exit {action.exit_fill}")
    if action.pnl_dollars is not None:
        parts.append(f"pnl ${action.pnl_dollars:.2f}")
    return " | ".join(parts)
