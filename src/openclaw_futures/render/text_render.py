"""Plain-text rendering for CLI and help output."""
from __future__ import annotations

from openclaw_futures.config import CONTRACT_SPECS
from openclaw_futures.models import AccountPlan, MarketSnapshot, RejectedSetup, SetupCandidate, StatsSummary, TradeAction, TradeIdea, TradePlan


def render_help() -> str:
    return "\n".join(
        [
            "TradingClaw Futures",
            "",
            "TradingClaw is a local futures analysis engine for MCL and M6E.",
            "It does not configure OpenClaw, does not log into Discord, and execution is manual only.",
            "Live testing currently supports cached EUR/USD bars for M6E scanning only.",
            "",
            "HTTP endpoints:",
            "GET /health",
            "GET /help",
            "POST /setups",
            "POST /levels",
            "POST /account",
            "POST /plan",
            "GET /ideas",
            "GET /ideas/{idea_id}",
            "POST /ideas/{idea_id}/take",
            "POST /ideas/{idea_id}/skip",
            "POST /ideas/{idea_id}/invalidate",
            "POST /ideas/{idea_id}/result",
            "GET /stats",
            "POST /reasoning-context",
            "POST /sync/run",
            "GET /sync/status",
            "POST /scan/run",
            "GET /scan/status",
            "",
            "Statuses:",
            "proposed -> taken",
            "proposed -> skipped",
            "proposed -> invalidated",
            "taken -> win/loss/breakeven",
            "",
            "CLI commands:",
            "tradingclaw-futures sync run",
            "tradingclaw-futures sync status",
            "tradingclaw-futures scan run",
            "tradingclaw-futures scan status",
            "",
            "Idea IDs:",
            "Stable numeric IDs are assigned from SQLite when a plan is persisted.",
            "Idea IDs are then used for take/skip/invalidate/result actions.",
            "",
            "OpenClaw compatibility:",
            "OpenClaw can consume TradingClaw API responses externally,",
            "but TradingClaw does not manage OpenClaw configuration or lifecycle.",
        ]
    )


def render_setups(setups: list[SetupCandidate], rejected_setups: list[RejectedSetup]) -> str:
    lines = ["TradingClaw Setups"]
    if setups:
        lines.append("Valid setups:")
        for setup in setups:
            lines.append(_setup_line(setup))
    else:
        lines.append("Valid setups: none")
    if rejected_setups:
        lines.append("")
        lines.append("Rejected setups:")
        for rejected in rejected_setups:
            lines.append(f"{rejected.symbol} {rejected.bias} {rejected.setup_type} | {'; '.join(rejected.rejection_reasons)}")
    return "\n".join(lines)


def render_levels(snapshots: list[MarketSnapshot]) -> str:
    lines = ["TradingClaw Levels"]
    for snapshot in snapshots:
        spec = CONTRACT_SPECS[snapshot.symbol]
        lines.append(
            f"{snapshot.symbol} | overnight {fmt(snapshot.overnight_low, spec.price_decimals)}-{fmt(snapshot.overnight_high, spec.price_decimals)}"
            f" | prior day {fmt(snapshot.prior_day_low, spec.price_decimals)}-{fmt(snapshot.prior_day_high, spec.price_decimals)}"
            f" | invalidation {fmt(snapshot.invalidation_low, spec.price_decimals)}-{fmt(snapshot.invalidation_high, spec.price_decimals)}"
        )
    return "\n".join(lines)


def render_account(plan: AccountPlan) -> str:
    lines = [
        "TradingClaw Account Plan",
        f"Account size: ${plan.account_size:.2f}",
        f"Risk budget: {plan.risk_percent:.2f}% (${plan.risk_budget:.2f})",
        f"Daily loss cap: ${plan.daily_loss_cap:.2f}",
        f"Max open risk: ${plan.max_open_risk:.2f}",
    ]
    for allocation in plan.allocations:
        lines.append(
            f"{allocation.label}: {allocation.total_contracts} total | MCL {allocation.mcl_contracts} | M6E {allocation.m6e_contracts}"
            f" | risk ${allocation.estimated_risk:.2f} | reward ${allocation.estimated_reward:.2f}"
        )
    return "\n".join(lines)


def render_plan(plan: TradePlan, ideas: list[TradeIdea] | None = None) -> str:
    lines = [
        "TradingClaw Plan",
        f"Source room: {plan.source_room}",
        "",
        render_account(plan.account_plan),
        "",
        render_setups(plan.setups, plan.rejected_setups),
        "",
        "Do-not-trade conditions:",
    ]
    lines.extend(f"- {condition}" for condition in plan.do_not_trade_conditions)
    if ideas:
        lines.append("")
        lines.append("Persisted ideas:")
        lines.extend(_idea_line(idea) for idea in ideas)
    return "\n".join(lines)


def render_ideas(ideas: list[TradeIdea]) -> str:
    lines = ["TradingClaw Ideas"]
    if not ideas:
        lines.append("No ideas recorded.")
        return "\n".join(lines)
    lines.extend(_idea_line(idea) for idea in ideas)
    return "\n".join(lines)


def render_idea_detail(idea: TradeIdea, actions: list[TradeAction]) -> str:
    lines = [
        "TradingClaw Idea",
        _idea_line(idea),
    ]
    if actions:
        lines.append("Actions:")
        lines.extend(_action_line(action) for action in actions)
    return "\n".join(lines)


def render_transition_summary(idea: TradeIdea, action: TradeAction | None = None) -> str:
    line = f"idea_id={idea.idea_id} | {idea.symbol} {idea.bias} | status {idea.status}"
    if action is None:
        return line
    suffix = [f"action {action.action_type}"]
    if action.contracts is not None:
        suffix.append(f"contracts {action.contracts}")
    if action.entry_fill is not None:
        suffix.append(f"entry {action.entry_fill}")
    if action.exit_fill is not None:
        suffix.append(f"exit {action.exit_fill}")
    if action.pnl_dollars is not None:
        suffix.append(f"pnl ${action.pnl_dollars:.2f}")
    return f"{line} | {' | '.join(suffix)}"


def render_stats(stats: StatsSummary) -> str:
    return "\n".join(
        [
            "TradingClaw Stats",
            f"Total ideas: {stats.total_ideas}",
            f"Proposed: {stats.proposed}",
            f"Taken: {stats.taken}",
            f"Skipped: {stats.skipped}",
            f"Invalidated: {stats.invalidated}",
            f"Wins: {stats.wins}",
            f"Losses: {stats.losses}",
            f"Breakeven: {stats.breakeven}",
            f"Realized PnL: ${stats.realized_pnl:.2f}",
            f"Average realized PnL: ${stats.average_pnl:.2f}",
        ]
    )


def render_sync_status(status: dict[str, object]) -> str:
    window = status["sync_window"]
    summary = status.get("last_sync_summary") or {}
    lines = [
        "TradingClaw Sync Status",
        f"Provider: {status.get('provider', 'twelvedata')}",
        f"Symbol: {status.get('symbol')}",
        f"Interval: {status.get('interval') or '?'}",
        f"Backfill days: {status.get('backfill_days')}",
        f"Latest cached timestamp: {status.get('latest_cached_timestamp') or 'none'}",
        f"Sync window: {window['start']}-{window['end']} | active {window['active']}",
        f"Last sync time: {status.get('last_sync_time') or 'never'}",
    ]
    if summary:
        lines.append(
            f"Last sync summary: mode {summary.get('sync_mode')} | fetched {summary.get('fetched_bars')} | stored changes {summary.get('stored_changes')}"
        )
    return "\n".join(lines)


def render_scan_status(status: dict[str, object]) -> str:
    window = status["alert_window"]
    summary = status.get("last_scan_result_summary") or {}
    lines = [
        "TradingClaw Scan Status",
        f"Symbol: {status.get('symbol')}",
        f"Interval: {status.get('interval') or '?'}",
        f"Alert window: {window['start']}-{window['end']} | active {status.get('active')}",
        f"Last scan time: {status.get('last_scan_time') or 'never'}",
    ]
    if summary:
        lines.append(
            f"Last scan summary: bars {summary.get('bars_used')} | valid setups {summary.get('valid_setups')} | persisted ideas {len(summary.get('persisted_idea_ids', []))}"
        )
    return "\n".join(lines)


def render_window_state(
    *,
    alert_window_active: bool,
    manual_override: bool,
    persist_requested: bool,
    webhook_requested: bool,
) -> str:
    lines = [
        "TradingClaw Scan Run",
        f"Alert window active: {alert_window_active}",
        f"Manual override used: {manual_override}",
        f"Persist requested: {persist_requested}",
        f"Webhook requested: {webhook_requested}",
    ]
    if not alert_window_active and not manual_override:
        lines.append("Outside the alert window, so scan output is informational only.")
    return "\n".join(lines)


def fmt(value: float | None, decimals: int) -> str:
    if value is None:
        return "?"
    return f"{value:.{decimals}f}"


def _setup_line(setup: SetupCandidate) -> str:
    spec = CONTRACT_SPECS[setup.symbol]
    return (
        f"{setup.symbol} {setup.bias} {setup.setup_type}"
        f" | entry {fmt(setup.entry_min, spec.price_decimals)}-{fmt(setup.entry_max, spec.price_decimals)}"
        f" | stop {fmt(setup.stop, spec.price_decimals)}"
        f" | target {fmt(setup.target, spec.price_decimals)}"
        f" | RR {setup.rr:.2f}"
        f" | confidence {setup.confidence:.2f}"
    )


def _idea_line(idea: TradeIdea) -> str:
    return (
        f"idea_id={idea.idea_id} | {idea.symbol} {idea.bias}"
        f" | entry {idea.entry_min}-{idea.entry_max}"
        f" | stop {idea.stop}"
        f" | target {idea.target}"
        f" | RR {idea.rr:.2f}"
        f" | status {idea.status}"
    )


def _action_line(action: TradeAction) -> str:
    parts = [f"{action.action_type} @ {action.acted_at}"]
    if action.contracts is not None:
        parts.append(f"contracts {action.contracts}")
    if action.entry_fill is not None:
        parts.append(f"entry {action.entry_fill}")
    if action.exit_fill is not None:
        parts.append(f"exit {action.exit_fill}")
    if action.pnl_dollars is not None:
        parts.append(f"pnl ${action.pnl_dollars:.2f}")
    if action.notes:
        parts.append(action.notes)
    return " | ".join(parts)
