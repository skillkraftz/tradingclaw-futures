"""HTTP route handlers."""
from __future__ import annotations

from dataclasses import asdict

from openclaw_futures.integrations.openclaw_contracts import (
    build_trade_plan,
    idea_contract,
    load_snapshots,
    normalize_symbols,
    plan_contract,
    reasoning_context_contract,
    snapshot_contract,
    stats_contract,
)
from openclaw_futures.integrations.webhook import post_message
from openclaw_futures.render.assistant_render import render_assistant_ideas, render_assistant_setups
from openclaw_futures.render.text_render import render_account, render_help, render_ideas, render_levels, render_plan, render_setups, render_stats
from openclaw_futures.render.webhook_render import render_webhook_plan
from openclaw_futures.storage.ideas import create_trade_idea, list_trade_ideas, mark_invalidated, mark_skipped, mark_taken
from openclaw_futures.storage.results import record_trade_result
from openclaw_futures.storage.stats import calculate_stats


def health_handler(app, _body: dict[str, object]) -> dict[str, object]:
    return {"status": "ok", "service": "tradingclaw-futures", "room_label": app.config.room_label}


def help_handler(_app, _body: dict[str, object]) -> dict[str, object]:
    return {"help": render_help()}


def levels_handler(app, body: dict[str, object]) -> dict[str, object]:
    symbols = normalize_symbols(_as_symbols(body.get("symbols")))
    snapshots = load_snapshots(app.provider, symbols)
    return {
        "symbols": symbols,
        "levels": {snapshot.symbol: snapshot_contract(snapshot) for snapshot in snapshots},
        "text": render_levels(snapshots),
    }


def setups_handler(app, body: dict[str, object]) -> dict[str, object]:
    account_size = float(body.get("account_size", 10_000))
    source_room = str(body.get("source_room", app.config.room_label))
    symbols = normalize_symbols(_as_symbols(body.get("symbols")))
    plan = build_trade_plan(app.provider, account_size, symbols, source_room=source_room)
    return {
        "symbols": symbols,
        "valid_setups": [asdict(item) for item in plan.setups],
        "rejected_setups": [asdict(item) for item in plan.rejected_setups],
        "text": render_setups(plan.setups, plan.rejected_setups),
        "assistant_text": render_assistant_setups(plan.setups, plan.rejected_setups),
    }


def account_handler(app, body: dict[str, object]) -> dict[str, object]:
    account_size = float(body.get("account_size", 10_000))
    symbols = normalize_symbols(_as_symbols(body.get("symbols")))
    plan = build_trade_plan(app.provider, account_size, symbols, source_room=app.config.room_label)
    return {"account_plan": asdict(plan.account_plan), "text": render_account(plan.account_plan)}


def plan_handler(app, body: dict[str, object]) -> dict[str, object]:
    account_size = float(body.get("account_size", 10_000))
    source_room = str(body.get("source_room", app.config.room_label))
    persist_ideas = bool(body.get("persist_ideas", True))
    post_webhook = bool(body.get("post_webhook", False))
    symbols = normalize_symbols(_as_symbols(body.get("symbols")))
    plan = build_trade_plan(app.provider, account_size, symbols, source_room=source_room)
    ideas = [create_trade_idea(app.connection, source_room=source_room, setup=setup) for setup in plan.setups] if persist_ideas else []
    payload: dict[str, object] = {
        "plan": plan_contract(plan),
        "idea_ids": [idea.idea_id for idea in ideas],
        "ideas": [idea_contract(idea) for idea in ideas],
        "text": render_plan(plan, ideas),
        "assistant_text": render_assistant_setups(plan.setups, plan.rejected_setups),
    }
    if post_webhook:
        payload["webhook"] = post_message(app.config, render_webhook_plan(plan))
    return payload


def ideas_handler(app, body: dict[str, object]) -> dict[str, object]:
    ideas = list_trade_ideas(app.connection, status=body.get("status"), limit=int(body.get("limit", 50)))
    return {
        "ideas": [idea_contract(idea) for idea in ideas],
        "assistant_text": render_assistant_ideas(ideas),
        "text": render_ideas(ideas),
    }


def take_handler(app, idea_id: int, body: dict[str, object]) -> dict[str, object]:
    idea = mark_taken(
        app.connection,
        idea_id,
        contracts=body.get("contracts"),
        entry_fill=body.get("entry_fill"),
        notes=body.get("notes"),
    )
    return {"idea": idea_contract(idea)}


def skip_handler(app, idea_id: int, body: dict[str, object]) -> dict[str, object]:
    return {"idea": idea_contract(mark_skipped(app.connection, idea_id, notes=body.get("notes")))}


def invalidate_handler(app, idea_id: int, body: dict[str, object]) -> dict[str, object]:
    return {"idea": idea_contract(mark_invalidated(app.connection, idea_id, notes=body.get("notes")))}


def result_handler(app, idea_id: int, body: dict[str, object]) -> dict[str, object]:
    return {
        "idea": idea_contract(
            record_trade_result(
                app.connection,
                idea_id,
                result=str(body["result"]),
                exit_fill=body.get("exit_fill"),
                pnl_dollars=body.get("pnl_dollars"),
                notes=body.get("notes"),
            )
        )
    }


def stats_handler(app, _body: dict[str, object]) -> dict[str, object]:
    stats = calculate_stats(app.connection)
    return {"stats": stats_contract(stats), "text": render_stats(stats)}


def reasoning_context_handler(app, body: dict[str, object]) -> dict[str, object]:
    account_size = float(body.get("account_size", 10_000))
    source_room = str(body.get("source_room", app.config.room_label))
    symbols = normalize_symbols(_as_symbols(body.get("symbols")))
    plan = build_trade_plan(app.provider, account_size, symbols, source_room=source_room)
    stats = calculate_stats(app.connection)
    recent_ideas = list_trade_ideas(app.connection, limit=int(body.get("journal_limit", 10)))
    return {
        "reasoning_context": reasoning_context_contract(plan, symbols, stats=stats, recent_ideas=recent_ideas),
        "assistant_text": render_assistant_setups(plan.setups, plan.rejected_setups),
    }


def _as_symbols(raw: object) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw]
