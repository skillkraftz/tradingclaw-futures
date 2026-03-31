"""Account planning based on deterministic setup risk."""
from __future__ import annotations

from openclaw_futures.models import AccountPlan, SetupCandidate
from openclaw_futures.risk.contracts import suggest_contract_allocations


def build_account_plan(account_size: float, setups: list[SetupCandidate]) -> AccountPlan:
    if account_size <= 0:
        raise ValueError("account_size must be positive")

    if account_size < 500:
        risk_percent = 0.005
    elif account_size < 5_000:
        risk_percent = 0.0075
    else:
        risk_percent = 0.01

    risk_budget = round(account_size * risk_percent, 2)
    daily_loss_cap = round(account_size * (risk_percent * 2.5), 2)
    max_open_risk = round(account_size * (risk_percent * 1.5), 2)
    allocations = suggest_contract_allocations(account_size, setups)
    notes = [
        "Sizing suggestions assume manual execution only.",
        "Daily loss cap is deterministic and should not be exceeded.",
        "Prefer mixed MCL/M6E exposure over concentrating the full budget in one contract.",
    ]
    if not allocations:
        notes.append("No allocation is available until at least one valid setup exists.")
    return AccountPlan(
        account_size=round(account_size, 2),
        risk_percent=round(risk_percent * 100, 2),
        risk_budget=risk_budget,
        daily_loss_cap=daily_loss_cap,
        max_open_risk=max_open_risk,
        allocations=allocations,
        notes=notes,
    )
