from __future__ import annotations

from openclaw_futures.analysis.setups import best_setups
from openclaw_futures.risk.account_plan import build_account_plan
from openclaw_futures.risk.contracts import suggest_contract_allocations


def test_contract_sizing_is_deterministic(provider) -> None:
    setups = best_setups([provider.get_snapshot("MCL"), provider.get_snapshot("M6E")])
    allocations_a = suggest_contract_allocations(10_000, setups)
    allocations_b = suggest_contract_allocations(10_000, setups)
    assert allocations_a == allocations_b


def test_account_plan_contains_caps_and_allocations(provider) -> None:
    setups = best_setups([provider.get_snapshot("MCL"), provider.get_snapshot("M6E")])
    plan = build_account_plan(7_500, setups)
    assert plan.risk_budget > 0
    assert plan.daily_loss_cap > plan.risk_budget
    assert len(plan.allocations) == 3
    assert any(allocation.mcl_contracts > 0 and allocation.m6e_contracts > 0 for allocation in plan.allocations)
