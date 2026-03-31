"""Discord slash commands."""
from __future__ import annotations

import discord
from discord import app_commands

from openclaw_futures.analysis.setups import best_setups
from openclaw_futures.models import TradePlan
from openclaw_futures.render.discord_render import (
    render_account,
    render_levels,
    render_plan,
    render_setups,
    render_trades,
)
from openclaw_futures.risk.account_plan import build_account_plan


def register_commands(tree: app_commands.CommandTree, service) -> None:
    @tree.command(name="trades", description="Show deterministic contract allocation suggestions.")
    @app_commands.describe(account_size="Account size in USD")
    async def trades(interaction: discord.Interaction, account_size: float) -> None:
        content = await build_trades_response(service, account_size)
        await interaction.response.send_message(content)

    @tree.command(name="setups", description="Show best futures setups.")
    @app_commands.describe(symbol="Optional symbol filter: MCL or M6E")
    async def setups(interaction: discord.Interaction, symbol: str | None = None) -> None:
        content = await build_setups_response(service, symbol)
        await interaction.response.send_message(content)

    @tree.command(name="levels", description="Show key levels and invalidation zones.")
    async def levels(interaction: discord.Interaction) -> None:
        content = await build_levels_response(service)
        await interaction.response.send_message(content)

    @tree.command(name="account", description="Show account risk settings.")
    @app_commands.describe(account_size="Account size in USD")
    async def account(interaction: discord.Interaction, account_size: float) -> None:
        content = await build_account_response(service, account_size)
        await interaction.response.send_message(content)

    @tree.command(name="plan", description="Show combined setups, sizing, and do-not-trade conditions.")
    @app_commands.describe(account_size="Account size in USD")
    async def plan(interaction: discord.Interaction, account_size: float) -> None:
        content = await build_plan_response(service, account_size)
        await interaction.response.send_message(content)


async def build_trades_response(service, account_size: float) -> str:
    setups = best_setups(service.load_snapshots())
    plan = build_account_plan(account_size, setups)
    return render_trades(plan)


async def build_setups_response(service, symbol: str | None = None) -> str:
    normalized = symbol.upper() if symbol else None
    return render_setups(best_setups(service.load_snapshots(), normalized), normalized)


async def build_levels_response(service) -> str:
    return render_levels(service.load_snapshots())


async def build_account_response(service, account_size: float) -> str:
    setups = best_setups(service.load_snapshots())
    plan = build_account_plan(account_size, setups)
    return render_account(plan)


async def build_plan_response(service, account_size: float) -> str:
    snapshots = service.load_snapshots()
    setups = best_setups(snapshots)
    account_plan = build_account_plan(account_size, setups)
    trade_plan = TradePlan(
        account_plan=account_plan,
        setups=setups,
        do_not_trade_conditions=service.do_not_trade_conditions(snapshots, setups),
        level_summary={snapshot.symbol: snapshot for snapshot in snapshots},
    )
    return render_plan(trade_plan)
