#!/usr/bin/env python3
"""Helper for calling TradingClaw locally and optionally forwarding to OpenClaw."""
from __future__ import annotations

from openclaw_futures.integrations.openclaw_bridge import run_bridge_command


if __name__ == "__main__":
    raise SystemExit(print(run_bridge_command()) or 0)
