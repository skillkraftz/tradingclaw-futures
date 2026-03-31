"""Compact assistant-friendly rendering."""
from __future__ import annotations

from openclaw_futures.models import RejectedSetup, SetupCandidate, TradeIdea


def render_assistant_setups(setups: list[SetupCandidate], rejected_setups: list[RejectedSetup]) -> str:
    lines: list[str] = []
    for setup in setups:
        lines.append(
            f"idea ID pending | {setup.symbol} | {setup.bias} | entry {setup.entry_min}-{setup.entry_max} | stop {setup.stop} | target {setup.target} | RR {setup.rr:.2f} | confidence {setup.confidence:.2f} | status valid"
        )
        if setup.notes:
            lines.append(f"notes: {'; '.join(setup.notes)}")
    for rejected in rejected_setups:
        lines.append(f"{rejected.symbol} | {rejected.bias} | status rejected | reasons: {'; '.join(rejected.rejection_reasons)}")
    return "\n".join(lines)


def render_assistant_ideas(ideas: list[TradeIdea]) -> str:
    return "\n".join(
        f"idea_id {idea.idea_id} | {idea.symbol} | {idea.bias} | RR {idea.rr:.2f} | {_assistant_idea_state(idea)}"
        for idea in ideas
    )


def _assistant_idea_state(idea: TradeIdea) -> str:
    if idea.status == "alerted":
        return "status alerted"
    if idea.alert_sent:
        return f"status {idea.status} | alerted"
    if idea.alert_attempted_at and idea.alert_error:
        return f"status {idea.status} | alert failed: {idea.alert_error}"
    return f"status {idea.status} | not alerted"
