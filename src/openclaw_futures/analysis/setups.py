"""Deterministic MCL and M6E setup generation."""
from __future__ import annotations

from openclaw_futures.analysis.scoring import MIN_SCORE, compute_setup_score, room_is_valid
from openclaw_futures.config import CONTRACT_SPECS
from openclaw_futures.models import MarketSnapshot, RejectedSetup, SetupCandidate


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


def evaluate_setups(snapshot: MarketSnapshot) -> tuple[list[SetupCandidate], list[RejectedSetup]]:
    spec = CONTRACT_SPECS[snapshot.symbol]
    minimum_atr = (spec.atr_threshold_ticks * spec.tick_size) / 2
    if snapshot.atr is None or snapshot.atr < minimum_atr:
        reason = "ATR unavailable." if snapshot.atr is None else f"ATR below minimum threshold of {minimum_atr:.{spec.price_decimals}f}."
        rejected = [
            RejectedSetup(
                symbol=snapshot.symbol,
                bias=bias,
                setup_type="range_breakout_pullback",
                rejection_reasons=[reason],
                notes=list(snapshot.notes),
            )
            for bias in ("bullish", "bearish")
        ]
        return [], rejected

    valid_candidates: list[SetupCandidate] = []
    rejected_candidates: list[RejectedSetup] = []
    for bias in ("bullish", "bearish"):
        trigger = snapshot.overnight_high if bias == "bullish" else snapshot.overnight_low
        if trigger is None:
            rejected_candidates.append(
                RejectedSetup(
                    symbol=snapshot.symbol,
                    bias=bias,
                    setup_type="range_breakout_pullback",
                    rejection_reasons=["Overnight trigger level unavailable."],
                    notes=list(snapshot.notes),
                )
            )
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

        candidate = _candidate_shell(
            snapshot=snapshot,
            bias=bias,
            entry=entry,
            stop=stop,
            target=target,
            rr=rr,
            risk_per_contract=risk_per_contract,
            reward_per_contract=reward_per_contract,
        )

        reasons: list[str] = []
        notes = [
            f"trigger={round(trigger, spec.price_decimals)}",
            f"atr={round(snapshot.atr, spec.price_decimals)}",
        ]
        if rr < 3.0:
            reasons.append("Reward-to-risk is below the explicit 1:3 requirement.")

        opposing = snapshot.prior_day_high if bias == "bullish" else snapshot.prior_day_low
        if not room_is_valid(candidate, opposing):
            reasons.append("Insufficient room before the opposing prior-day level.")

        score = compute_setup_score(snapshot, candidate)
        confidence = round(min(max(score, 0) / 100, 0.99), 2)
        if score < MIN_SCORE:
            reasons.append(f"Setup score {score} is below minimum threshold {MIN_SCORE}.")

        if reasons:
            rejected_candidates.append(
                RejectedSetup(
                    symbol=snapshot.symbol,
                    bias=bias,
                    setup_type=candidate.setup_type,
                    rejection_reasons=reasons,
                    entry_min=candidate.entry_min,
                    entry_max=candidate.entry_max,
                    stop=candidate.stop,
                    target=candidate.target,
                    rr=candidate.rr,
                    confidence=confidence,
                    notes=notes,
                )
            )
            continue

        valid_candidates.append(
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
                notes=notes + ["meets explicit 1:3 requirement"],
                valid=True,
                score=score,
            )
        )

    return (
        sorted(valid_candidates, key=lambda item: (item.score, item.confidence), reverse=True),
        sorted(rejected_candidates, key=lambda item: (item.symbol, item.bias)),
    )


def generate_setups(snapshot: MarketSnapshot) -> list[SetupCandidate]:
    candidates, _ = evaluate_setups(snapshot)
    return candidates


def best_setups(snapshots: list[MarketSnapshot], symbol: str | None = None) -> list[SetupCandidate]:
    selected = [snap for snap in snapshots if symbol is None or snap.symbol == symbol]
    setups = [setup for snap in selected for setup in generate_setups(snap)]
    return sorted(setups, key=lambda item: (item.score, item.rr, item.confidence), reverse=True)


def _points_to_dollars(symbol: str, points: float) -> float:
    spec = CONTRACT_SPECS[symbol]
    ticks = points / spec.tick_size
    return ticks * spec.tick_value


def _candidate_shell(
    snapshot: MarketSnapshot,
    bias: str,
    entry: float,
    stop: float,
    target: float,
    rr: float,
    risk_per_contract: float,
    reward_per_contract: float,
) -> SetupCandidate:
    spec = CONTRACT_SPECS[snapshot.symbol]
    return SetupCandidate(
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
        notes=[],
        valid=rr >= 3.0,
        score=0,
    )
