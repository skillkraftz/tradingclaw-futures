"""CLI entrypoint for TradingClaw Futures."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from openclaw_futures.api.app import run_server
from openclaw_futures.config import AppConfig
from openclaw_futures.integrations.openclaw_contracts import build_trade_plan, idea_contract, reasoning_context_contract
from openclaw_futures.providers.file_provider import FileMarketDataProvider
from openclaw_futures.render.text_render import render_account, render_help, render_ideas, render_levels, render_plan, render_setups, render_stats
from openclaw_futures.services.scanner import ScannerService
from openclaw_futures.storage.db import connect
from openclaw_futures.storage.ideas import create_trade_idea, list_trade_ideas, mark_invalidated, mark_skipped, mark_taken
from openclaw_futures.storage.results import record_trade_result
from openclaw_futures.storage.stats import calculate_stats


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_env()

    if args.command == "serve":
        run_server(config)
        return 0

    provider = FileMarketDataProvider(config.data_dir)
    connection = connect(config.db_path)
    scanner = ScannerService(config, connection)

    if args.command == "help":
        print(render_help())
        return 0
    if args.command == "levels":
        snapshots = [provider.get_snapshot(symbol) for symbol in args.symbols]
        print(render_levels(snapshots))
        return 0
    if args.command == "setups":
        plan = build_trade_plan(provider, args.account_size, args.symbols, source_room=config.room_label)
        print(render_setups(plan.setups, plan.rejected_setups))
        return 0
    if args.command == "account":
        plan = build_trade_plan(provider, args.account_size, args.symbols, source_room=config.room_label)
        print(json.dumps(asdict(plan.account_plan), indent=2) if args.json else render_account(plan.account_plan))
        return 0
    if args.command == "plan":
        plan = build_trade_plan(provider, args.account_size, args.symbols, source_room=args.source_room or config.room_label)
        ideas = [create_trade_idea(connection, source_room=plan.source_room, setup=setup) for setup in plan.setups] if args.persist else []
        print(json.dumps({"plan": asdict(plan), "ideas": [idea_contract(idea) for idea in ideas]}, indent=2) if args.json else render_plan(plan, ideas))
        return 0
    if args.command == "ideas":
        ideas = list_trade_ideas(connection, status=args.status, limit=args.limit)
        print(json.dumps([idea_contract(idea) for idea in ideas], indent=2) if args.json else render_ideas(ideas))
        return 0
    if args.command == "take":
        print(json.dumps(idea_contract(mark_taken(connection, args.idea_id, contracts=args.contracts, entry_fill=args.entry_fill, notes=args.notes)), indent=2))
        return 0
    if args.command == "skip":
        print(json.dumps(idea_contract(mark_skipped(connection, args.idea_id, notes=args.notes)), indent=2))
        return 0
    if args.command == "invalidate":
        print(json.dumps(idea_contract(mark_invalidated(connection, args.idea_id, notes=args.notes)), indent=2))
        return 0
    if args.command == "result":
        print(
            json.dumps(
                idea_contract(
                    record_trade_result(
                        connection,
                        args.idea_id,
                        result=args.result,
                        exit_fill=args.exit_fill,
                        pnl_dollars=args.pnl_dollars,
                        notes=args.notes,
                    )
                ),
                indent=2,
            )
        )
        return 0
    if args.command == "stats":
        stats = calculate_stats(connection)
        print(json.dumps(asdict(stats), indent=2) if args.json else render_stats(stats))
        return 0
    if args.command == "sync":
        if args.sync_command == "run":
            payload = scanner.run_sync(
                force_full_backfill=args.force_full_backfill,
                days=args.days,
                interval_override=args.interval_override,
                symbol_override=args.symbol_override,
            )
            print(json.dumps(payload, indent=2) if args.json else payload["text"])
            return 0
        if args.sync_command == "status":
            payload = scanner.get_sync_status(symbol=args.symbol)
            print(json.dumps(payload, indent=2) if args.json else payload["text"])
            return 0
    if args.command == "scan":
        if args.scan_command == "run":
            payload = scanner.run_scan(
                account_size=args.account_size,
                persist_ideas=args.persist_ideas,
                post_webhook_flag=args.post_webhook,
                source_room=args.source_room or config.room_label,
                allow_outside_window=args.allow_outside_window,
            )
            print(json.dumps(payload, indent=2) if args.json else payload["text"])
            return 0
        if args.scan_command == "status":
            payload = scanner.get_scan_status(symbol=args.symbol)
            print(json.dumps(payload, indent=2) if args.json else payload["text"])
            return 0
    if args.command == "reasoning-context":
        plan = build_trade_plan(provider, args.account_size, args.symbols, source_room=config.room_label)
        stats = calculate_stats(connection)
        ideas = list_trade_ideas(connection, limit=args.limit)
        print(json.dumps(reasoning_context_contract(plan, args.symbols, stats=stats, recent_ideas=ideas), indent=2))
        return 0

    print(render_help())
    return 0


def serve_main() -> int:
    run_server(AppConfig.from_env())
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradingclaw-futures", description="TradingClaw Futures local engine")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help")
    subparsers.add_parser("serve")

    levels = subparsers.add_parser("levels")
    levels.add_argument("--symbols", nargs="+", default=["MCL", "M6E"])

    setups = subparsers.add_parser("setups")
    setups.add_argument("--account-size", type=float, default=10000)
    setups.add_argument("--symbols", nargs="+", default=["MCL", "M6E"])

    account = subparsers.add_parser("account")
    account.add_argument("--account-size", type=float, required=True)
    account.add_argument("--symbols", nargs="+", default=["MCL", "M6E"])
    account.add_argument("--json", action="store_true")

    plan = subparsers.add_parser("plan")
    plan.add_argument("--account-size", type=float, required=True)
    plan.add_argument("--symbols", nargs="+", default=["MCL", "M6E"])
    plan.add_argument("--source-room")
    plan.add_argument("--persist", action="store_true")
    plan.add_argument("--json", action="store_true")

    ideas = subparsers.add_parser("ideas")
    ideas.add_argument("--status")
    ideas.add_argument("--limit", type=int, default=50)
    ideas.add_argument("--json", action="store_true")

    take = subparsers.add_parser("take")
    take.add_argument("idea_id", type=int)
    take.add_argument("--contracts", type=int)
    take.add_argument("--entry-fill", type=float)
    take.add_argument("--notes")

    skip = subparsers.add_parser("skip")
    skip.add_argument("idea_id", type=int)
    skip.add_argument("--notes")

    invalidate = subparsers.add_parser("invalidate")
    invalidate.add_argument("idea_id", type=int)
    invalidate.add_argument("--notes")

    result = subparsers.add_parser("result")
    result.add_argument("idea_id", type=int)
    result.add_argument("--result", required=True, choices=["win", "loss", "breakeven"])
    result.add_argument("--exit-fill", type=float)
    result.add_argument("--pnl-dollars", type=float)
    result.add_argument("--notes")

    stats = subparsers.add_parser("stats")
    stats.add_argument("--json", action="store_true")

    sync = subparsers.add_parser("sync")
    sync_subparsers = sync.add_subparsers(dest="sync_command")
    sync_run = sync_subparsers.add_parser("run")
    sync_run.add_argument("--force-full-backfill", action="store_true")
    sync_run.add_argument("--days", type=int)
    sync_run.add_argument("--interval-override")
    sync_run.add_argument("--symbol-override")
    sync_run.add_argument("--json", action="store_true")
    sync_status = sync_subparsers.add_parser("status")
    sync_status.add_argument("--symbol")
    sync_status.add_argument("--json", action="store_true")

    scan = subparsers.add_parser("scan")
    scan_subparsers = scan.add_subparsers(dest="scan_command")
    scan_run = scan_subparsers.add_parser("run")
    scan_run.add_argument("--account-size", type=float, default=10_000)
    scan_run.add_argument("--persist-ideas", action="store_true")
    scan_run.add_argument("--post-webhook", action="store_true")
    scan_run.add_argument("--source-room")
    scan_run.add_argument("--allow-outside-window", action="store_true")
    scan_run.add_argument("--json", action="store_true")
    scan_status = scan_subparsers.add_parser("status")
    scan_status.add_argument("--symbol")
    scan_status.add_argument("--json", action="store_true")

    reasoning = subparsers.add_parser("reasoning-context")
    reasoning.add_argument("--account-size", type=float, required=True)
    reasoning.add_argument("--symbols", nargs="+", default=["MCL", "M6E"])
    reasoning.add_argument("--limit", type=int, default=10)

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
