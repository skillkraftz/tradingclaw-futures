from __future__ import annotations

from openclaw_futures.integrations.openclaw_contracts import build_trade_plan, load_snapshots
from openclaw_futures.render.assistant_render import render_assistant_setups
from openclaw_futures.render.text_render import render_help, render_levels, render_plan, render_setups


def test_render_setups_contains_rr_and_rejections(provider) -> None:
    plan = build_trade_plan(provider, 10000)
    rendered = render_setups(plan.setups, plan.rejected_setups)
    assert "RR 3.00" in rendered
    assert "Rejected setups:" in rendered


def test_render_levels_contains_invalidation(provider) -> None:
    rendered = render_levels(load_snapshots(provider))
    assert "invalidation" in rendered
    assert "MCL" in rendered
    assert "M6E" in rendered


def test_render_plan_and_assistant_output(provider) -> None:
    plan = build_trade_plan(provider, 12000)
    rendered = render_plan(plan)
    assistant = render_assistant_setups(plan.setups, plan.rejected_setups)
    assert "Do-not-trade conditions" in rendered
    assert "status valid" in assistant


def test_render_help_mentions_openclaw_boundary() -> None:
    rendered = render_help()
    assert "does not configure OpenClaw" in rendered
