"""Webhook rendering helpers."""
from __future__ import annotations

from openclaw_futures.models import TradePlan


def render_webhook_plan(plan: TradePlan) -> str:
    lines = [f"TradingClaw plan for {plan.source_room}"]
    for setup in plan.setups:
        lines.append(
            f"{setup.symbol} {setup.bias} entry {setup.entry_min}-{setup.entry_max} stop {setup.stop} target {setup.target} RR {setup.rr:.2f}"
        )
    if not plan.setups:
        lines.append("No valid setups.")
    return "\n".join(lines)
