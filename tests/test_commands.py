from __future__ import annotations

import pytest

from openclaw_futures.discord.commands.core import (
    build_account_response,
    build_levels_response,
    build_plan_response,
    build_setups_response,
    build_trades_response,
)


@pytest.mark.asyncio
async def test_trades_command_response(service) -> None:
    content = await build_trades_response(service, 10_000)
    assert "Conservative" in content
    assert "reward" in content


@pytest.mark.asyncio
async def test_setups_command_response(service) -> None:
    content = await build_setups_response(service, "M6E")
    assert "M6E" in content
    assert "RR 3.00" in content


@pytest.mark.asyncio
async def test_levels_command_response(service) -> None:
    content = await build_levels_response(service)
    assert "Key Levels" in content
    assert "invalidation" in content


@pytest.mark.asyncio
async def test_account_command_response(service) -> None:
    content = await build_account_response(service, 5_000)
    assert "Risk budget" in content
    assert "Daily loss cap" in content


@pytest.mark.asyncio
async def test_plan_command_response(service) -> None:
    content = await build_plan_response(service, 15_000)
    assert "OpenClaw Futures Plan" in content
    assert "Do-not-trade conditions" in content
