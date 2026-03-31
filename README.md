# tradingclaw-futures

`tradingclaw-futures` is a local futures analysis engine for deterministic manual trade planning in `MCL` and `M6E`.

It is not a Discord bot, does not require a Discord token, does not modify `openclaw.json`, and does not manage OpenClaw. OpenClaw can call TradingClaw externally over HTTP and can optionally pass TradingClaw output to Codex for additional reasoning or summarization.

## Scope

- Futures only: `MCL` and `M6E`
- Manual execution only
- Deterministic 1:3 reward-to-risk setup generation
- Stable invalidation and account sizing logic
- Pluggable market data providers
- Local HTTP API
- Optional CLI for debugging and admin actions
- Persistent SQLite trade journal
- Optional webhook posting when configured

## Package Layout

```text
src/openclaw_futures/
  api/
    app.py
    routes.py
  cli.py
  config.py
  models.py
  providers/
    base.py
    file_provider.py
  analysis/
    mcl_levels.py
    m6e_levels.py
    setups.py
    scoring.py
  risk/
    contracts.py
    account_plan.py
  storage/
    db.py
    ideas.py
    results.py
    stats.py
  integrations/
    webhook.py
    openclaw_contracts.py
  render/
    text_render.py
    webhook_render.py
    assistant_render.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
pytest
```

## Config

TradingClaw uses package-local environment variables only:

```bash
TRADINGCLAW_HOST=127.0.0.1
TRADINGCLAW_PORT=8787
TRADINGCLAW_DATA_DIR=./data/fixtures
TRADINGCLAW_DEFAULT_PROVIDER=file
TRADINGCLAW_DB_PATH=./data/runtime/tradingclaw.sqlite3
TRADINGCLAW_WEBHOOK_URL=
TRADINGCLAW_WEBHOOK_THREAD_ID=
TRADINGCLAW_ROOM_LABEL=trading-room
TRADINGCLAW_LOG_LEVEL=INFO
```

Webhook settings are optional. If they are absent, TradingClaw still works fully as a local engine.

## Local Usage

Run the API:

```bash
tradingclaw-futures serve
```

Run CLI help:

```bash
tradingclaw-futures help
```

Generate a plan and persist ideas:

```bash
tradingclaw-futures plan --account-size 10000 --persist
```

Inspect reasoning context:

```bash
tradingclaw-futures reasoning-context --account-size 10000 --symbols MCL M6E
```

## HTTP API

- `GET /health`
- `GET /help`
- `POST /setups`
- `POST /levels`
- `POST /account`
- `POST /plan`
- `GET /ideas`
- `POST /ideas/{idea_id}/take`
- `POST /ideas/{idea_id}/skip`
- `POST /ideas/{idea_id}/invalidate`
- `POST /ideas/{idea_id}/result`
- `GET /stats`
- `POST /reasoning-context`

`POST /plan` can persist valid setups as `proposed` ideas and returns stable numeric `idea_id` values from SQLite.

## SQLite Journal

TradingClaw persists:

- `trade_ideas`
- `trade_actions`

Supported status transitions:

- `proposed -> taken`
- `proposed -> skipped`
- `proposed -> invalidated`
- `taken -> win`
- `taken -> loss`
- `taken -> breakeven`

## Reasoning Context

`POST /reasoning-context` returns a compact deterministic object for external AI or orchestration layers such as OpenClaw. It includes:

- account size
- requested symbols
- valid setups
- rejected setups and rejection reasons
- major levels
- invalidation zones
- do-not-trade conditions
- contract sizing summary
- journal/status summary

TradingClaw prepares this context but does not make a model call itself.

## Example OpenClaw Workflow

1. OpenClaw receives a Discord request.
2. OpenClaw calls TradingClaw on `localhost`.
3. TradingClaw returns deterministic setup, risk, journal, and reasoning-context data.
4. OpenClaw presents that output directly or forwards the reasoning context to Codex for explanation.
5. Trade execution remains manual outside both systems.

## Notes

- TradingClaw does not place orders.
- It does not include broker APIs.
- It does not include Tradovate integration.
- It does not run as a separate Discord bot.
- OpenClaw integration is external and optional.
