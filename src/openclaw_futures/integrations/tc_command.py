"""Strict one-shot command interface for OpenClaw -> TradingClaw handoff."""
from __future__ import annotations

import shlex

from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_bridge import TradingClawApiClient


COMMAND_HELP = "\n".join(
    [
        "TradingClaw Commands",
        "tc help",
        "tc sync run",
        "tc sync status",
        "tc scan status",
        "tc scan test [account_size]",
        "tc ideas",
        "tc idea <idea_id>",
        "tc result <idea_id> <win|loss|breakeven> [pnl_dollars]",
        "tc stats",
    ]
)

COMMAND_EXAMPLES = "\n".join(
    [
        "Examples:",
        "tc help",
        "tc sync run",
        "tc scan test 1500",
        "tc ideas",
        "tc idea 3",
        "tc result 3 win 50",
    ]
)


def run_tc_command(
    command: str,
    *,
    config: AppConfig | None = None,
    client: TradingClawApiClient | None = None,
) -> str:
    tokens = _normalize_tokens(command)
    if not tokens or tokens == ["help"]:
        return _prefixed_help()

    cfg = config or AppConfig.from_env()
    api_client = client or TradingClawApiClient.from_config(cfg)

    try:
        if tokens == ["sync", "run"]:
            payload = api_client.request("POST", "/sync/run", {})
            return _render_sync(payload, title="TradingClaw Sync Run")
        if tokens == ["sync", "status"]:
            payload = api_client.request("GET", "/sync/status")
            return _render_sync(payload, title="TradingClaw Sync Status")
        if tokens == ["scan", "status"]:
            payload = api_client.request("GET", "/scan/status")
            return _render_scan(payload, title="TradingClaw Scan Status", forced=False)
        if len(tokens) in {2, 3} and tokens[:2] == ["scan", "test"]:
            account_size = float(tokens[2]) if len(tokens) == 3 else 10_000.0
            payload = api_client.request(
                "POST",
                "/scan/run",
                {
                    "account_size": account_size,
                    "persist_ideas": True,
                    "post_webhook": True,
                    "allow_outside_window": True,
                },
            )
            return _render_scan(payload, title="TradingClaw Test Scan", forced=True)
        if tokens == ["ideas"]:
            payload = api_client.request("GET", "/ideas")
            return _render_ideas(payload)
        if len(tokens) == 2 and tokens[0] == "idea":
            payload = api_client.request("GET", f"/ideas/{int(tokens[1])}")
            return _render_idea_detail(payload)
        if len(tokens) in {3, 4} and tokens[0] == "result":
            idea_id = int(tokens[1])
            result = tokens[2]
            if result not in {"win", "loss", "breakeven"}:
                raise ValueError("result must be win, loss, or breakeven")
            body: dict[str, object] = {"result": result}
            if len(tokens) == 4:
                body["pnl_dollars"] = float(tokens[3])
            payload = api_client.request("POST", f"/ideas/{idea_id}/result", body)
            return _render_result(payload)
        if tokens == ["stats"]:
            payload = api_client.request("GET", "/stats")
            return _render_stats(payload)
    except ValueError as exc:
        return _invalid_command(f"invalid command: {exc}")
    except RuntimeError as exc:
        return f"TradingClaw Error\n{exc}"

    return _invalid_command("unsupported command")


def _normalize_tokens(command: str) -> list[str]:
    tokens = shlex.split(command.strip())
    if tokens and tokens[0] == "tc":
        tokens = tokens[1:]
    return tokens


def _prefixed_help() -> str:
    return f"{COMMAND_HELP}\n\n{COMMAND_EXAMPLES}"


def _invalid_command(message: str) -> str:
    return f"TradingClaw Command Error\n{message}\n\n{COMMAND_EXAMPLES}"


def _render_sync(payload: dict[str, object], *, title: str) -> str:
    summary = payload.get("last_sync_summary") or {}
    lines = [
        title,
        f"watchlist: {', '.join(payload.get('watchlist', []))}",
        f"last sync: {payload.get('last_sync_time') or 'never'}",
        f"fetched: {summary.get('fetched_bars', 0)} | stored: {summary.get('stored_changes', 0)}",
    ]
    for symbol, details in payload.get("symbols", {}).items():
        line = (
            f"{symbol} | {details.get('interval') or '?'} | latest {details.get('latest_cached_timestamp') or 'none'}"
        )
        if details.get("stored_changes") is not None:
            line += f" | stored {details.get('stored_changes', 0)}"
        if details.get("error"):
            line += f" | error {details['error']}"
        lines.append(line)
    return "\n".join(lines)


def _render_scan(payload: dict[str, object], *, title: str, forced: bool) -> str:
    summary = payload.get("last_scan_result_summary") or {}
    lines = [
        title,
        (
            "forced: outside-window override on | persist on | webhook on"
            if forced
            else f"alert window active: {payload.get('alert_window_active')}"
        ),
        f"watchlist: {', '.join(payload.get('watchlist', []))}",
        (
            f"detected: {payload.get('detected', 0)} | persisted: {payload.get('persisted_ideas', 0)}"
            f" | alerted: {payload.get('alerted_ideas', 0)} | alert failures: {payload.get('alert_failures', 0)}"
        ),
    ]
    if payload.get("idea_ids"):
        lines.append(f"idea ids: {', '.join(str(item) for item in payload['idea_ids'])}")
    webhook = payload.get("webhook") or summary.get("webhook")
    if isinstance(webhook, dict) and webhook.get("reason"):
        lines.append(f"alert detail: {webhook['reason']}")
    for symbol, details in payload.get("symbols", {}).items():
        line = (
            f"{symbol} | valid {details.get('valid_setups', 0)}"
            f" | persisted {details.get('persisted_ideas', 0)}"
            f" | alerted {len(details.get('alerted_idea_ids', []))}"
        )
        if details.get("error"):
            line += f" | error {details['error']}"
        lines.append(line)
    return "\n".join(lines)


def _render_ideas(payload: dict[str, object]) -> str:
    ideas = payload.get("ideas", [])
    lines = ["TradingClaw Ideas"]
    if not ideas:
        lines.append("no ideas recorded")
        return "\n".join(lines)
    for idea in ideas:
        lines.append(_idea_line(idea))
    return "\n".join(lines)


def _render_idea_detail(payload: dict[str, object]) -> str:
    idea = payload["idea"]
    actions = payload.get("actions", [])
    lines = ["TradingClaw Idea", _idea_line(idea)]
    if actions:
        last = actions[-1]
        action_line = f"last action: {last['action_type']} @ {last['acted_at']}"
        if last.get("pnl_dollars") is not None:
            action_line += f" | pnl ${float(last['pnl_dollars']):.2f}"
        lines.append(action_line)
    return "\n".join(lines)


def _render_result(payload: dict[str, object]) -> str:
    idea = payload["idea"]
    lines = ["TradingClaw Result", _idea_line(idea)]
    if payload.get("webhook", {}).get("reason"):
        lines.append(f"webhook: {payload['webhook']['reason']}")
    return "\n".join(lines)


def _render_stats(payload: dict[str, object]) -> str:
    stats = payload["stats"]
    return "\n".join(
        [
            "TradingClaw Stats",
            (
                f"ideas {stats['total_ideas']} | detected {stats['detected']} | alerted {stats['alerted']}"
                f" | taken {stats['taken']}"
            ),
            (
                f"wins {stats['wins']} | losses {stats['losses']} | breakeven {stats['breakeven']}"
                f" | pnl ${float(stats['realized_pnl']):.2f}"
            ),
        ]
    )


def _idea_line(idea: dict[str, object]) -> str:
    return (
        f"#{idea['idea_id']} {idea['symbol']} {idea['bias']} | RR {float(idea['rr']):.2f}"
        f" | { _alert_state(idea) }"
    )


def _alert_state(idea: dict[str, object]) -> str:
    if idea.get("status") == "alerted":
        return "status alerted"
    if idea.get("alert_sent"):
        return f"status {idea['status']} | alerted"
    if idea.get("alert_error"):
        return f"status {idea['status']} | alert failed"
    return f"status {idea['status']} | not alerted"
