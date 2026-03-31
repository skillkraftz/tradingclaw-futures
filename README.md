# tradingclaw-futures

`tradingclaw-futures` is a local futures analysis engine for deterministic manual trade planning in `MCL` and `M6E`.

It is not a Discord bot, does not require a Discord token, does not modify `openclaw.json`, and does not manage OpenClaw. OpenClaw can call TradingClaw externally over HTTP and can optionally pass TradingClaw output to Codex for explanation or summarization.

## What Is Implemented

- Futures only: `MCL` and `M6E`
- Manual execution only
- Deterministic 1:3 reward-to-risk setup generation
- Stable invalidation and account sizing logic
- File-backed market data provider
- Local HTTP API using Python stdlib `wsgiref`
- Optional CLI for local debugging and admin actions
- Persistent SQLite trade journal
- Optional webhook posting with `thread_id` support

## Fresh Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
pytest -q
```

Runtime dependencies are currently empty. The package uses only the Python standard library at runtime.

## Configuration

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

If `TRADINGCLAW_WEBHOOK_URL` is unset, TradingClaw still works fully in local-only mode.

## Start The API

```bash
source .venv/bin/activate
tradingclaw-futures serve
```

Alternative entrypoint:

```bash
source .venv/bin/activate
tradingclaw-futures-api
```

The server binds to `http://127.0.0.1:8787` by default.

## CLI Examples

Show built-in help:

```bash
tradingclaw-futures help
```

Show current levels:

```bash
tradingclaw-futures levels --symbols MCL M6E
```

Show setups without persisting:

```bash
tradingclaw-futures setups --account-size 10000 --symbols MCL M6E
```

Generate and persist a plan:

```bash
tradingclaw-futures plan --account-size 10000 --persist
```

API note: `POST /plan` is preview-only by default. Persisting ideas requires `"persist_ideas": true`.

Inspect persisted ideas:

```bash
tradingclaw-futures ideas --json
```

Take, skip, invalidate, and result actions:

```bash
tradingclaw-futures take 3 --contracts 1 --entry-fill 72.18
tradingclaw-futures skip 1 --notes "standing down"
tradingclaw-futures invalidate 2 --notes "price left zone"
tradingclaw-futures result 3 --result win --exit-fill 72.86 --pnl-dollars 67.5
tradingclaw-futures result 4 --result breakeven --exit-fill 1.08220 --pnl-dollars 0
tradingclaw-futures result 5 --result loss --exit-fill 71.96 --pnl-dollars=-22.5
```

Get reasoning context for OpenClaw or another orchestrator:

```bash
tradingclaw-futures reasoning-context --account-size 10000 --symbols MCL M6E
```

Show journal stats:

```bash
tradingclaw-futures stats
```

## HTTP API

Implemented endpoints:

- `GET /health`
- `GET /help`
- `POST /setups`
- `POST /levels`
- `POST /account`
- `POST /plan`
- `GET /ideas`
- `GET /ideas/{idea_id}`
- `POST /ideas/{idea_id}/take`
- `POST /ideas/{idea_id}/skip`
- `POST /ideas/{idea_id}/invalidate`
- `POST /ideas/{idea_id}/result`
- `GET /stats`
- `POST /reasoning-context`

Health check:

```bash
curl -s http://127.0.0.1:8787/health
```

Help output:

```bash
curl -s http://127.0.0.1:8787/help
```

Plan generation with persistence:

```bash
curl -s -X POST http://127.0.0.1:8787/plan \
  -H 'Content-Type: application/json' \
  -d '{"account_size":10000,"persist_ideas":true}'
```

Plan preview without persistence:

```bash
curl -s -X POST http://127.0.0.1:8787/plan \
  -H 'Content-Type: application/json' \
  -d '{"account_size":10000}'
```

Reasoning context:

```bash
curl -s -X POST http://127.0.0.1:8787/reasoning-context \
  -H 'Content-Type: application/json' \
  -d '{"account_size":10000,"symbols":["MCL","M6E"]}'
```

Take an idea:

```bash
curl -s -X POST http://127.0.0.1:8787/ideas/3/take \
  -H 'Content-Type: application/json' \
  -d '{"contracts":1,"entry_fill":72.18}'
```

Record a result:

```bash
curl -s -X POST http://127.0.0.1:8787/ideas/3/result \
  -H 'Content-Type: application/json' \
  -d '{"result":"win","exit_fill":72.86,"pnl_dollars":67.5}'
```

List ideas and stats:

```bash
curl -s http://127.0.0.1:8787/ideas
curl -s 'http://127.0.0.1:8787/ideas?status=win&limit=10'
curl -s http://127.0.0.1:8787/ideas/3
curl -s http://127.0.0.1:8787/stats
```

## Idea Lifecycle

Persisted ideas use stable numeric `idea_id` values from SQLite.
Repeated `POST /plan` calls with `"persist_ideas": true` use a simple deterministic dedupe for identical still-proposed ideas from the same day and `source_room`.

Supported transitions:

- `proposed -> taken`
- `proposed -> skipped`
- `proposed -> invalidated`
- `taken -> win`
- `taken -> loss`
- `taken -> breakeven`

SQLite tables:

- `trade_ideas`
- `trade_actions`

The parent directory for `TRADINGCLAW_DB_PATH` is created automatically on first run.

## Reasoning Context

`POST /reasoning-context` returns a compact deterministic payload for OpenClaw or another orchestration layer. It includes:

- account size
- requested symbols
- valid setups
- rejected setups and rejection reasons
- major levels
- invalidation zones
- do-not-trade conditions
- contract sizing summary
- journal status summary

TradingClaw prepares the context only. It does not make model calls itself.

## Webhook Usage

Webhook posting is optional and only happens when explicitly requested in `POST /plan` with `"post_webhook": true`.

Example local request with webhook enabled by environment:

```bash
export TRADINGCLAW_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export TRADINGCLAW_WEBHOOK_THREAD_ID="123456789012345678"

curl -s -X POST http://127.0.0.1:8787/plan \
  -H 'Content-Type: application/json' \
  -d '{"account_size":10000,"persist_ideas":true,"post_webhook":true}'
```

Implemented behavior:

- When no webhook URL is configured, TradingClaw returns a structured `"sent": false` webhook result and still completes the plan request.
- When `TRADINGCLAW_WEBHOOK_THREAD_ID` is set, TradingClaw appends `thread_id=...` to the webhook URL.
- The webhook payload contains rendered text only. It does not alter journal state.
- Lifecycle endpoints also support optional `"post_webhook": true`:
  - `POST /ideas/{idea_id}/take`
  - `POST /ideas/{idea_id}/skip`
  - `POST /ideas/{idea_id}/invalidate`
  - `POST /ideas/{idea_id}/result`

## Example OpenClaw Workflow

1. OpenClaw receives a Discord request.
2. OpenClaw calls TradingClaw over `localhost`.
3. TradingClaw returns deterministic setups, levels, risk, persistence state, or reasoning context.
4. OpenClaw presents that output directly, or forwards the reasoning-context payload to Codex for explanation.
5. Trade execution remains manual outside both systems.

## Troubleshooting

Missing runtime directory:

- Set `TRADINGCLAW_DB_PATH` to the intended SQLite file.
- TradingClaw creates the parent directory automatically when opening the DB.

Bad fixture data:

- The file provider raises `ValueError` for malformed JSON or CSV fixtures.
- Verify `TRADINGCLAW_DATA_DIR` and the expected `mcl_*` / `m6e_*` files.

Webhook unset:

- Leave `TRADINGCLAW_WEBHOOK_URL=` blank for local-only mode.
- `POST /plan` still succeeds; the webhook result reports `"sent": false`.

Port already in use:

- Set a different `TRADINGCLAW_PORT`.
- Restart the server with the new value.

Negative PnL on CLI:

- Pass negative values as `--pnl-dollars=-22.5` to avoid shell ambiguity.

## Notes

- TradingClaw does not place orders.
- It does not include broker APIs.
- It does not include Tradovate integration.
- It does not run as a separate Discord bot.
- OpenClaw integration is external and optional.
