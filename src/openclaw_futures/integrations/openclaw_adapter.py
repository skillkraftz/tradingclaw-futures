"""Strict local command adapter for OpenClaw-style TradingClaw calls."""
from __future__ import annotations

import shlex

from openclaw_futures.api.app import TradingClawApp, create_app


USAGE = "\n".join(
    [
        "TradingClaw adapter commands:",
        "tc plan <account_size>",
        "tc ideas",
        "tc idea <idea_id>",
        "tc take <idea_id> <contracts>",
        "tc skip <idea_id>",
        "tc result <idea_id> <win|loss|breakeven> <pnl_dollars>",
        "tc stats",
    ]
)


def handle_command(command: str) -> str:
    return _handle_command(command, create_app())


def _handle_command(command: str, app: TradingClawApp) -> str:
    tokens = shlex.split(command)
    if not tokens:
        return USAGE
    if tokens[0] != "tc":
        return "TradingClaw adapter requires commands starting with 'tc'.\n\n" + USAGE
    if len(tokens) == 1:
        return USAGE

    action = tokens[1]
    try:
        if action == "plan" and len(tokens) == 3:
            status, payload = app.dispatch("POST", "/plan", {"account_size": _as_float(tokens[2])})
            return _text_response(status, payload)
        if action == "ideas" and len(tokens) == 2:
            status, payload = app.dispatch("GET", "/ideas", {})
            return _text_response(status, payload)
        if action == "idea" and len(tokens) == 3:
            status, payload = app.dispatch("GET", f"/ideas/{_as_int(tokens[2])}", {})
            return _text_response(status, payload)
        if action == "take" and len(tokens) == 4:
            idea_id = _as_int(tokens[2])
            contracts = _as_int(tokens[3])
            status, payload = app.dispatch("POST", f"/ideas/{idea_id}/take", {"contracts": contracts})
            return _text_response(status, payload)
        if action == "skip" and len(tokens) == 3:
            idea_id = _as_int(tokens[2])
            status, payload = app.dispatch("POST", f"/ideas/{idea_id}/skip", {})
            return _text_response(status, payload)
        if action == "result" and len(tokens) == 5:
            idea_id = _as_int(tokens[2])
            result = tokens[3]
            pnl_dollars = _as_float(tokens[4])
            status, payload = app.dispatch(
                "POST",
                f"/ideas/{idea_id}/result",
                {"result": result, "pnl_dollars": pnl_dollars},
            )
            return _text_response(status, payload)
        if action == "stats" and len(tokens) == 2:
            status, payload = app.dispatch("GET", "/stats", {})
            return _text_response(status, payload)
    except (ValueError, FileNotFoundError) as exc:
        return f"TradingClaw command error: {exc}"

    return "TradingClaw adapter received an unsupported command.\n\n" + USAGE


def _text_response(status: int, payload: dict[str, object]) -> str:
    if status >= 400:
        return f"TradingClaw API error {status}: {payload.get('error', 'unknown error')}"
    for key in ("text", "help", "assistant_text"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return str(payload)


def _as_int(value: str) -> int:
    return int(value)


def _as_float(value: str) -> float:
    return float(value)
