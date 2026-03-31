"""Local bridge between TradingClaw HTTP API and optional OpenClaw reasoning."""
from __future__ import annotations

import argparse
import json
from urllib import error, request

from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_client import OpenClawClient
from openclaw_futures.integrations.reasoning_payloads import build_reasoning_payload


class TradingClawApiClient:
    def __init__(self, base_url: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: AppConfig) -> "TradingClawApiClient":
        return cls(f"http://{config.host}:{config.port}")

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload or {}).encode("utf-8") if method.upper() == "POST" else None
        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method=method.upper(),
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                return json.loads(raw)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            detail = json.loads(raw) if raw else {"error": exc.reason}
            raise RuntimeError(f"TradingClaw API error {exc.code}: {detail.get('error', exc.reason)}") from exc
        except (error.URLError, OSError) as exc:
            raise RuntimeError(f"TradingClaw API request failed: {exc}") from exc


def run_bridge_command(argv: list[str] | None = None, *, config: AppConfig | None = None) -> str:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cfg = config or AppConfig.from_env()
    tradingclaw = TradingClawApiClient.from_config(cfg)
    openclaw = OpenClawClient.from_config(cfg)

    command_label, payload = _dispatch_bridge_command(args, tradingclaw)
    lines = [_render_primary(payload)]
    if args.reason and openclaw.enabled:
        reasoning_payload = build_reasoning_payload(command=command_label, tradingclaw_response=payload)
        reasoning_result = openclaw.submit_reasoning(reasoning_payload)
        if reasoning_result.get("sent"):
            response = reasoning_result.get("response")
            lines.append("")
            lines.append("OpenClaw reasoning:")
            lines.append(json.dumps(response, indent=2) if response is not None else "OpenClaw accepted the payload.")
        else:
            lines.append("")
            lines.append(f"OpenClaw reasoning unavailable: {reasoning_result.get('reason', 'unknown error')}")
    return "\n".join(lines)


def _dispatch_bridge_command(args, client: TradingClawApiClient) -> tuple[str, dict[str, object]]:
    if args.command == "sync":
        if args.sync_command == "run":
            return "sync run", client.request("POST", "/sync/run", {})
        return "sync status", client.request("GET", "/sync/status")
    if args.command == "scan":
        if args.scan_command == "run":
            return "scan run", client.request(
                "POST",
                "/scan/run",
                {
                    "account_size": args.account_size,
                    "persist_ideas": args.persist_ideas,
                    "post_webhook": args.post_webhook,
                    "allow_outside_window": args.allow_outside_window,
                },
            )
        return "scan status", client.request("GET", "/scan/status")
    if args.command == "plan":
        return "plan", client.request("POST", "/plan", {"account_size": args.account_size})
    if args.command == "ideas":
        return "ideas", client.request("GET", "/ideas")
    if args.command == "idea":
        return "idea", client.request("GET", f"/ideas/{args.idea_id}")
    if args.command == "result":
        return "result", client.request(
            "POST",
            f"/ideas/{args.idea_id}/result",
            {"result": args.result, "pnl_dollars": args.pnl_dollars},
        )
    if args.command == "stats":
        return "stats", client.request("GET", "/stats")
    raise ValueError(f"unsupported bridge command={args.command!r}")


def _render_primary(payload: dict[str, object]) -> str:
    for key in ("text", "help", "assistant_text"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return json.dumps(payload, indent=2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw-bridge", description="TradingClaw/OpenClaw local bridge")
    parser.add_argument("--reason", action="store_true", help="Submit a reasoning payload to OpenClaw when enabled")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync")
    sync_subparsers = sync.add_subparsers(dest="sync_command", required=True)
    sync_subparsers.add_parser("run")
    sync_subparsers.add_parser("status")

    scan = subparsers.add_parser("scan")
    scan_subparsers = scan.add_subparsers(dest="scan_command", required=True)
    scan_run = scan_subparsers.add_parser("run")
    scan_run.add_argument("--account-size", type=float, default=10_000)
    scan_run.add_argument("--persist-ideas", action="store_true")
    scan_run.add_argument("--post-webhook", action="store_true")
    scan_run.add_argument("--allow-outside-window", action="store_true")
    scan_subparsers.add_parser("status")

    plan = subparsers.add_parser("plan")
    plan.add_argument("account_size", type=float)

    subparsers.add_parser("ideas")

    idea = subparsers.add_parser("idea")
    idea.add_argument("idea_id", type=int)

    result = subparsers.add_parser("result")
    result.add_argument("idea_id", type=int)
    result.add_argument("result", choices=["win", "loss", "breakeven"])
    result.add_argument("pnl_dollars", type=float)

    subparsers.add_parser("stats")
    return parser
