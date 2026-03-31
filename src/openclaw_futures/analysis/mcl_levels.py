"""MCL-specific level analysis."""
from __future__ import annotations

from openclaw_futures.analysis.scoring import atr
from openclaw_futures.models import Bar, MarketSnapshot


def build_mcl_snapshot(bars: list[Bar]) -> MarketSnapshot:
    return _build_snapshot("MCL", bars)


def _build_snapshot(symbol: str, bars: list[Bar]) -> MarketSnapshot:
    if not bars:
        raise ValueError("bars are required")

    today = bars[-1].ts[:10]
    overnight = [bar for bar in bars if bar.ts[:10] == today and bar.ts[11:] < "09:30:00"]
    prior_dates = {bar.ts[:10] for bar in bars if bar.ts[:10] < today}
    prior_date = max(prior_dates) if prior_dates else None
    prior_day = [bar for bar in bars if prior_date and bar.ts[:10] == prior_date]
    daily_open_bar = next((bar for bar in bars if bar.ts[:10] == today), bars[-1])
    atr_value = atr(bars)
    invalidation_pad = max((atr_value or 0.18) * 0.5, 0.08)
    overnight_high = max((bar.high for bar in overnight), default=None)
    overnight_low = min((bar.low for bar in overnight), default=None)
    return MarketSnapshot(
        symbol=symbol,
        bars=bars,
        overnight_high=overnight_high,
        overnight_low=overnight_low,
        prior_day_high=max((bar.high for bar in prior_day), default=None),
        prior_day_low=min((bar.low for bar in prior_day), default=None),
        daily_open=daily_open_bar.open,
        last_price=bars[-1].close,
        atr=atr_value,
        invalidation_high=(overnight_high + invalidation_pad) if overnight_high is not None else None,
        invalidation_low=(overnight_low - invalidation_pad) if overnight_low is not None else None,
        notes=[
            "MCL uses micro crude oil tick economics.",
            "Prior-day and overnight levels are derived from fixture bars.",
        ],
    )
