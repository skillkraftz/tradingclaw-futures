"""Deterministic contract sizing suggestions."""
from __future__ import annotations

from openclaw_futures.models import ContractAllocation, SetupCandidate


def suggest_contract_allocations(account_size: float, setups: list[SetupCandidate]) -> list[ContractAllocation]:
    if account_size <= 0:
        raise ValueError("account_size must be positive")

    mcl_risk = _risk_for_symbol(setups, "MCL")
    m6e_risk = _risk_for_symbol(setups, "M6E")
    baseline_risk = min(mcl_risk, m6e_risk)

    profiles = (
        ("conservative", 0.005),
        ("balanced", 0.01),
        ("aggressive", 0.015),
    )
    allocations: list[ContractAllocation] = []
    for label, risk_pct in profiles:
        budget = account_size * risk_pct
        raw_total = max(int(budget // baseline_risk), 1)
        total_contracts = min(raw_total, 6)
        if total_contracts == 1:
            mcl_contracts = 1 if mcl_risk <= m6e_risk else 0
            m6e_contracts = total_contracts - mcl_contracts
        else:
            mcl_contracts = max(1, round(total_contracts * 0.6))
            m6e_contracts = max(1, total_contracts - mcl_contracts)
        if mcl_contracts + m6e_contracts > total_contracts:
            mcl_contracts = max(0, mcl_contracts - 1)
        if mcl_contracts + m6e_contracts < total_contracts:
            m6e_contracts += total_contracts - (mcl_contracts + m6e_contracts)

        estimated_risk = round((mcl_contracts * mcl_risk) + (m6e_contracts * m6e_risk), 2)
        estimated_reward = round(estimated_risk * 3, 2)
        allocations.append(
            ContractAllocation(
                label=label,
                total_contracts=total_contracts,
                mcl_contracts=mcl_contracts,
                m6e_contracts=m6e_contracts,
                estimated_risk=estimated_risk,
                estimated_reward=estimated_reward,
            )
        )
    return allocations


def _risk_for_symbol(setups: list[SetupCandidate], symbol: str) -> float:
    for setup in setups:
        if setup.symbol == symbol and setup.valid:
            return setup.risk_per_contract
    valid_risks = [setup.risk_per_contract for setup in setups if setup.valid]
    if not valid_risks:
        raise ValueError("at least one valid setup is required for contract sizing")
    return min(valid_risks)
