from __future__ import annotations

import pytest

from openclaw_futures.analysis.setups import best_setups, generate_setups, setup_reward_ratio


def test_rr_calculation_is_exact_for_bullish() -> None:
    rr = setup_reward_ratio(entry=72.18, stop=72.03, target=72.63, bias="bullish")
    assert rr == pytest.approx(3.0)


def test_rr_calculation_is_exact_for_bearish() -> None:
    rr = setup_reward_ratio(entry=1.08140, stop=1.08220, target=1.07900, bias="bearish")
    assert rr == pytest.approx(3.0)


def test_generated_setups_are_valid_and_sorted(provider) -> None:
    setups = best_setups([provider.get_snapshot("MCL"), provider.get_snapshot("M6E")])
    assert setups
    assert all(setup.rr >= 3.0 for setup in setups)
    assert all(setup.valid for setup in setups)
    assert setups == sorted(setups, key=lambda item: (item.score, item.rr, item.confidence), reverse=True)


def test_generate_setups_from_snapshot(provider) -> None:
    snapshot = provider.get_snapshot("MCL")
    setups = generate_setups(snapshot)
    assert setups
    first = setups[0]
    assert first.symbol == "MCL"
    assert first.risk_per_contract > 0
    assert first.reward_per_contract == pytest.approx(first.risk_per_contract * 3, abs=0.02)
