#!/usr/bin/env python3
"""Single strict TradingClaw command entrypoint for OpenClaw tool use."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_futures.integrations.tc_command import run_tc_command


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = " ".join(args).strip()
    print(run_tc_command(command))
    return 0 if command else 2


if __name__ == "__main__":
    raise SystemExit(main())
