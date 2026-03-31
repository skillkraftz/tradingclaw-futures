"""Deterministic scoring for futures setup candidates."""
from __future__ import annotations

import math

from openclaw_futures.models import Bar, MarketSnapshot, SetupCandidate


MIN_SCORE = 65
ROOM_VALIDITY_R = 2.5


def atr(bars: list[Bar], period: int = 14) -> float | None:
    """Simple-average ATR for deterministic behavior."""
    if len(bars) < period + 1:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(bars)):
        prev_close = bars[index - 1].close
        bar = bars[index]
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
        )
    return sum(true_ranges[-period:]) / period


def moving_average(closes: list[float], period: int) -> list[float]:
    values = [float("nan")] * len(closes)
    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1 : index + 1]
        values[index] = sum(window) / period
    return values


def room_is_valid(candidate: SetupCandidate, opposing_level: float | None) -> bool:
    if opposing_level is None:
        return True
    price_risk = _price_risk(candidate)
    if candidate.bias == "bullish":
        if candidate.entry_max < opposing_level < candidate.target:
            return (opposing_level - candidate.entry_max) >= ROOM_VALIDITY_R * price_risk
    else:
        if candidate.target < opposing_level < candidate.entry_min:
            return (candidate.entry_min - opposing_level) >= ROOM_VALIDITY_R * price_risk
    return True


def compute_setup_score(snapshot: MarketSnapshot, candidate: SetupCandidate) -> int:
    closes = [bar.close for bar in snapshot.bars]
    ma20 = moving_average(closes, 20)
    valid_ma = [value for value in ma20 if not math.isnan(value)]
    if len(valid_ma) >= 11:
        slope = ma20[-1] - ma20[-10]
        trend = 25 if (candidate.bias == "bullish" and slope > 0) or (candidate.bias == "bearish" and slope < 0) else 10
    else:
        trend = 15

    if snapshot.atr is None:
        volatility = 0
    elif candidate.risk_per_contract <= 0:
        volatility = 0
    elif snapshot.atr >= candidate.risk_per_contract / 3:
        volatility = 20
    else:
        volatility = 8

    if candidate.bias == "bullish":
        opposing = snapshot.prior_day_high
    else:
        opposing = snapshot.prior_day_low

    room = 30 if room_is_valid(candidate, opposing) else 0
    structure = 15 if snapshot.daily_open is not None else 10
    rr_quality = 10 if candidate.rr >= 3.0 else 0
    return trend + volatility + room + structure + rr_quality


def _price_risk(candidate: SetupCandidate) -> float:
    entry_reference = (candidate.entry_min + candidate.entry_max) / 2
    return abs(entry_reference - candidate.stop)
