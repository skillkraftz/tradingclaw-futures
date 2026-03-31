from __future__ import annotations

from openclaw_futures.analysis.setups import best_setups
from openclaw_futures.models import TradePlan
from openclaw_futures.render.discord_render import render_levels, render_plan, render_setups
from openclaw_futures.risk.account_plan import build_account_plan


def test_render_setups_contains_rr_and_score(provider) -> None:
    setups = best_setups([provider.get_snapshot("MCL"), provider.get_snapshot("M6E")])
    rendered = render_setups(setups)
    assert "RR 3.00" in rendered
    assert "score" in rendered


def test_render_levels_contains_invalidation(provider) -> None:
    rendered = render_levels([provider.get_snapshot("MCL"), provider.get_snapshot("M6E")])
    assert "invalidation" in rendered
    assert "MCL" in rendered
    assert "M6E" in rendered


def test_render_plan_includes_do_not_trade(provider, service) -> None:
    snapshots = service.load_snapshots()
    setups = best_setups(snapshots)
    account_plan = build_account_plan(12_000, setups)
    trade_plan = TradePlan(
        account_plan=account_plan,
        setups=setups,
        do_not_trade_conditions=service.do_not_trade_conditions(snapshots, setups),
        level_summary={snapshot.symbol: snapshot for snapshot in snapshots},
    )
    rendered = render_plan(trade_plan)
    assert "Do-not-trade conditions" in rendered
    assert "Contract split" in rendered
