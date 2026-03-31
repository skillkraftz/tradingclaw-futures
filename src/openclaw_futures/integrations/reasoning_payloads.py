"""Structured payload builders for OpenClaw/Codex reasoning."""
from __future__ import annotations

from openclaw_futures.models import StatsSummary, TradeIdea


def build_reasoning_payload(
    *,
    command: str,
    tradingclaw_response: dict[str, object],
    stats: StatsSummary | None = None,
    ideas: list[TradeIdea] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "tradingclaw-futures",
        "command": command,
        "tradingclaw_response": tradingclaw_response,
    }
    if "plan" in tradingclaw_response:
        payload["plan_summary"] = _plan_summary(tradingclaw_response)
    if "reasoning_context" in tradingclaw_response:
        payload["reasoning_context"] = tradingclaw_response["reasoning_context"]
    if "symbols" in tradingclaw_response:
        payload["symbol_summary"] = tradingclaw_response["symbols"]
    if "ideas" in tradingclaw_response:
        payload["ideas"] = tradingclaw_response["ideas"]
    if "stats" in tradingclaw_response:
        payload["stats"] = tradingclaw_response["stats"]
    if stats is not None:
        payload["stats"] = {
            "total_ideas": stats.total_ideas,
            "wins": stats.wins,
            "losses": stats.losses,
            "breakeven": stats.breakeven,
            "realized_pnl": stats.realized_pnl,
        }
    if ideas is not None:
        payload["recent_idea_ids"] = [idea.idea_id for idea in ideas]
    return payload


def _plan_summary(payload: dict[str, object]) -> dict[str, object]:
    plan = payload["plan"]
    if not isinstance(plan, dict):
        return {}
    valid_setups = plan.get("valid_setups", [])
    rejected_setups = plan.get("rejected_setups", [])
    return {
        "valid_setup_count": len(valid_setups) if isinstance(valid_setups, list) else 0,
        "rejected_setup_count": len(rejected_setups) if isinstance(rejected_setups, list) else 0,
        "symbols": sorted((plan.get("levels") or {}).keys()) if isinstance(plan.get("levels"), dict) else [],
        "do_not_trade_conditions": plan.get("do_not_trade_conditions", []),
    }
