"""Deterministic MCL and M6E setup generation."""
from __future__ import annotations

from openclaw_futures.analysis.scoring import MIN_SCORE, compute_setup_score, room_is_valid
from openclaw_futures.config import CONTRACT_SPECS
from openclaw_futures.models import MarketSnapshot, SetupCandidate


def setup_reward_ratio(entry: float, stop: float, target: float, bias: str) -> float:
    if bias == "bullish":
        risk = entry - stop
        reward = target - entry
    else:
        risk = stop - entry
        reward = entry - target
    if risk <= 0:
        return 0.0
    return reward / risk


def generate_setups(snapshot: MarketSnapshot) -> list[SetupCandidate]:
    spec = CONTRACT_SPECS[snapshot.symbol]
    if snapshot.atr is None or snapshot.atr < (spec.atr_threshold_ticks * spec.tick_size) / 2:
        return []

    candidates: list[SetupCandidate] = []
    for bias in ("bullish", "bearish"):
        trigger = snapshot.overnight_high if bias == "bullish" else snapshot.overnight_low
        if trigger is None:
            continue

        buffer_value = spec.entry_buffer_ticks * spec.tick_size
        min_stop = spec.min_stop_ticks * spec.tick_size
        entry = trigger + buffer_value if bias == "bullish" else trigger - buffer_value
        risk_points = max(snapshot.atr * spec.atr_multiplier, min_stop)
        stop = entry - risk_points if bias == "bullish" else entry + risk_points
        target = entry + (3 * risk_points) if bias == "bullish" else entry - (3 * risk_points)
        rr = setup_reward_ratio(entry, stop, target, bias)
        risk_per_contract = _points_to_dollars(snapshot.symbol, risk_points)
        reward_per_contract = round(risk_per_contract * rr, 2)
        candidate = SetupCandidate(
            symbol=snapshot.symbol,
            bias=bias,
            entry_min=round(entry - spec.tick_size, spec.price_decimals),
            entry_max=round(entry + spec.tick_size, spec.price_decimals),
            stop=round(stop, spec.price_decimals),
            target=round(target, spec.price_decimals),
            risk_per_contract=round(risk_per_contract, 2),
            reward_per_contract=round(reward_per_contract, 2),
            rr=round(rr, 2),
            confidence=0.0,
            setup_type="range_breakout_pullback",
            notes=[
                f"trigger={round(trigger, spec.price_decimals)}",
                f"atr={round(snapshot.atr, spec.price_decimals)}",
            ],
            valid=rr >= 3.0,
            score=0,
        )

        opposing = snapshot.prior_day_high if bias == "bullish" else snapshot.prior_day_low
        if not room_is_valid(candidate, opposing):
            continue

        score = compute_setup_score(snapshot, candidate)
        if score < MIN_SCORE:
            continue

        confidence = round(min(score / 100, 0.99), 2)
        notes = list(candidate.notes)
        if candidate.valid:
            notes.append("meets explicit 1:3 requirement")
        else:
            notes.append("fails explicit 1:3 requirement")

        candidates.append(
            SetupCandidate(
                symbol=candidate.symbol,
                bias=candidate.bias,
                entry_min=candidate.entry_min,
                entry_max=candidate.entry_max,
                stop=candidate.stop,
                target=candidate.target,
                risk_per_contract=candidate.risk_per_contract,
                reward_per_contract=candidate.reward_per_contract,
                rr=candidate.rr,
                confidence=confidence,
                setup_type=candidate.setup_type,
                notes=notes,
                valid=candidate.valid,
                score=score,
            )
        )

    return sorted(candidates, key=lambda item: (item.score, item.confidence), reverse=True)


def best_setups(snapshots: list[MarketSnapshot], symbol: str | None = None) -> list[SetupCandidate]:
    selected = [snap for snap in snapshots if symbol is None or snap.symbol == symbol]
    setups = [setup for snap in selected for setup in generate_setups(snap)]
    return sorted(setups, key=lambda item: (item.score, item.rr, item.confidence), reverse=True)


def _points_to_dollars(symbol: str, points: float) -> float:
    spec = CONTRACT_SPECS[symbol]
    ticks = points / spec.tick_size
    return ticks * spec.tick_value
