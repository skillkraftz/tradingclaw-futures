# tradingclaw-futures

`tradingclaw-futures` is a local futures analysis engine for deterministic manual trade planning in `MCL` and `M6E`.

It is not a Discord bot, does not require a Discord token, does not modify `openclaw.json`, and does not manage OpenClaw. OpenClaw can call TradingClaw externally over HTTP and can optionally pass TradingClaw output to Codex for explanation or summarization.

## What Is Implemented

- Futures only: `MCL` and `M6E`
- Manual execution only
- Deterministic 1:3 reward-to-risk setup generation
- Stable invalidation and account sizing logic
- File-backed market data provider
- Twelve Data live sync loop for a small Basic-plan watchlist
- Local HTTP API using Python stdlib `wsgiref`
- Optional CLI for local debugging and admin actions
- Persistent SQLite trade journal
- Persistent SQLite market-bar cache for live sync testing
- Optional OpenClaw gateway client for reasoning handoff
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
TRADINGCLAW_TWELVEDATA_API_KEY=
TRADINGCLAW_TWELVEDATA_BASE_URL=https://api.twelvedata.com
TRADINGCLAW_LIVE_SYMBOL=M6E
TRADINGCLAW_TWELVEDATA_M6E_SYMBOL=EUR/USD
TRADINGCLAW_TWELVEDATA_SYMBOLS=EUR/USD,SPY,BTC/USD,ETH/USD
TRADINGCLAW_PRIMARY_SYMBOL=EUR/USD
TRADINGCLAW_BACKFILL_DAYS=10
TRADINGCLAW_SYNC_START=08:00
TRADINGCLAW_SYNC_END=13:00
TRADINGCLAW_ALERT_START=08:30
TRADINGCLAW_ALERT_END=11:30
TRADINGCLAW_SCAN_INTERVAL_MINUTES=5
TRADINGCLAW_ALLOW_OUTSIDE_WINDOW_MANUAL_SCAN=true
TRADINGCLAW_OPENCLAW_ENABLED=false
TRADINGCLAW_OPENCLAW_BASE_URL=http://127.0.0.1:18789
TRADINGCLAW_OPENCLAW_REASONING_PATH=
TRADINGCLAW_OPENCLAW_AUTH_TOKEN=
TRADINGCLAW_OPENCLAW_AUTH_HEADER=Authorization
```

If `TRADINGCLAW_WEBHOOK_URL` is unset, TradingClaw still works fully in local-only mode.
If `TRADINGCLAW_TWELVEDATA_API_KEY` is unset, the original file-backed endpoints still work, but live sync fails clearly when invoked.

## Start The API

Recommended startup:

```bash
./start_tradingclaw.sh
```

Useful options:

```bash
./start_tradingclaw.sh --skip-tests
./start_tradingclaw.sh --provider file
./start_tradingclaw.sh --provider twelvedata --port 8787
```

The startup script verifies `python3`, creates `.venv` if needed, installs the package in editable mode, checks `.env`, optionally runs tests, prints diagnostics, and starts the API server.

Manual startup:

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

Run live watchlist sync and scan status:

```bash
tradingclaw-futures sync run
tradingclaw-futures sync status
tradingclaw-futures scan run --persist-ideas
tradingclaw-futures scan status
```

Use the local OpenClaw bridge helper:

```bash
python3 scripts/openclaw_bridge.py sync run
python3 scripts/openclaw_bridge.py scan status
python3 scripts/openclaw_bridge.py plan 1500
python3 scripts/openclaw_bridge.py stats
python3 scripts/openclaw_bridge.py --reason scan run
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
- `POST /sync/run`
- `GET /sync/status`
- `POST /scan/run`
- `GET /scan/status`

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

Live sync and scan:

```bash
curl -s -X POST http://127.0.0.1:8787/sync/run \
  -H 'Content-Type: application/json' \
  -d '{"days":10}'

curl -s http://127.0.0.1:8787/sync/status

curl -s -X POST http://127.0.0.1:8787/scan/run \
  -H 'Content-Type: application/json' \
  -d '{"account_size":10000,"persist_ideas":true,"allow_outside_window":true}'

curl -s http://127.0.0.1:8787/scan/status
```

## Live Watchlist Cache Loop

TradingClaw now supports a stateful local cache for Twelve Data Basic-plan testing across a small watchlist. This does not replace the file provider and it does not change the deterministic setup engine.

- First live sync performs an initial backfill using `TRADINGCLAW_BACKFILL_DAYS` and stores bars in SQLite.
- Later syncs append only missing bars from the latest cached timestamp for the active interval.
- The cache prefers `1min` bars and falls back to `5min` bars if Twelve Data does not return usable `1min` data.
- `scan` uses cached bars as the analysis input and builds deterministic proxy snapshots for:
  - `EUR/USD` as the `M6E` proxy
  - `SPY` as the `MES / ES` proxy
  - `BTC/USD` as the `MBT` proxy
  - `ETH/USD` as the `MET` proxy
- Proxy-symbol account sizing remains informational. The deterministic setup engine is still the source of truth, but this pass does not attempt instrument-specific futures sizing for `SPY`, `BTC/USD`, or `ETH/USD`.

### Why This Watchlist

- `EUR/USD`, `SPY`, `BTC/USD`, and `ETH/USD` fit Twelve Data Basic-plan categories without adding commodities or futures in this pass.
- They cover forex, US ETF/equity, and crypto, which is enough to exercise the cached multi-symbol sync loop without blowing up credit usage.
- A single 4-symbol batch request is materially cheaper and cleaner than separate one-symbol polling loops.

### Expected Credit Usage

- The implementation attempts batch `time_series` requests whenever multiple symbols share the same sync window and `start_date`.
- On a typical 5-minute cycle with all 4 watchlist symbols aligned, expect one `1min` batch request and only fall back to `5min` for symbols that need it.
- Incremental sync groups symbols by their latest cached timestamp so it can still batch where practical instead of forcing one request per symbol every cycle.

The live cache tables are:

- `market_bars`
- `runtime_state`

### Sync Window vs Alert Window

- Sync window controls when scheduled data refreshes should be considered active.
- Alert window controls when new trade ideas may be persisted or webhook-posted without override.
- Scans outside the alert window still run against cached data, but persistence and webhook actions are informational-only unless manual override is allowed.

### Debugging Outside Normal Hours

- Leave `TRADINGCLAW_ALLOW_OUTSIDE_WINDOW_MANUAL_SCAN=true` to allow manual `scan run` requests outside the alert window.
- Use `POST /scan/run` with `"allow_outside_window": true` for one-off debugging even if the default config is more restrictive.
- Sync status continues to show the configured sync window even when a manual sync is run outside that window.
- `/sync/status` and `/scan/status` now report the configured watchlist plus per-symbol interval and latest cached timestamp.

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
- `POST /scan/run` also supports optional `"post_webhook": true`, but webhook posting remains gated by the alert window unless manual override is allowed.

## Example OpenClaw Workflow

1. OpenClaw receives a Discord request.
2. OpenClaw calls TradingClaw over `localhost`.
3. TradingClaw returns deterministic setups, levels, sync/scan status, persistence state, or reasoning context.
4. TradingClaw may optionally package a structured reasoning payload and submit it to the local OpenClaw gateway.
5. OpenClaw presents that output directly, or forwards the reasoning payload to Codex for explanation or summarization.
6. Trade execution remains manual outside both systems.

OpenClaw remains the Discord-facing gateway. TradingClaw remains a standalone local engine and API.

### OpenClaw Gateway Config

TradingClaw does not assume any fixed OpenClaw route beyond the local base URL default. The reasoning handoff is fully configurable:

```bash
TRADINGCLAW_OPENCLAW_ENABLED=false
TRADINGCLAW_OPENCLAW_BASE_URL=http://127.0.0.1:18789
TRADINGCLAW_OPENCLAW_REASONING_PATH=
TRADINGCLAW_OPENCLAW_AUTH_TOKEN=
TRADINGCLAW_OPENCLAW_AUTH_HEADER=Authorization
```

- Leave `TRADINGCLAW_OPENCLAW_ENABLED=false` to keep TradingClaw fully local-only.
- Set `TRADINGCLAW_OPENCLAW_REASONING_PATH` only when you have a verified local OpenClaw reasoning endpoint.
- TradingClaw does not make any Discord assumptions and does not require changes to `openclaw.json`.

### Local Bridge Usage

The bridge helper demonstrates the intended boundary:

- `scripts/openclaw_bridge.py`

Examples:

```bash
python3 scripts/openclaw_bridge.py sync run
python3 scripts/openclaw_bridge.py scan run --persist-ideas
python3 scripts/openclaw_bridge.py ideas
python3 scripts/openclaw_bridge.py idea 42
python3 scripts/openclaw_bridge.py result 42 win 86
python3 scripts/openclaw_bridge.py --reason stats
```

The bridge always calls TradingClaw over HTTP. If OpenClaw integration is enabled and the reasoning path is configured, it can also forward a structured reasoning payload to the local OpenClaw gateway.

## OpenClaw Command Integration

TradingClaw also provides a strict local command adapter for OpenClaw-side tool use in:

- `src/openclaw_futures/integrations/openclaw_adapter.py`

Primary entrypoint:

- `handle_command(command: str) -> str`

Supported command forms:

```text
tc plan 1500
tc ideas
tc idea 42
tc take 42 1
tc skip 42
tc result 42 win 86
tc stats
```

Behavior:

- Parsing is strict and deterministic.
- No LLM or natural language parsing is used inside TradingClaw.
- The adapter calls the existing local TradingClaw API dispatch layer and returns clean text output.

Examples:

```python
from openclaw_futures.integrations.openclaw_adapter import handle_command

print(handle_command("tc plan 1500"))
print(handle_command("tc ideas"))
print(handle_command("tc idea 42"))
print(handle_command("tc take 42 1"))
print(handle_command("tc skip 42"))
print(handle_command("tc result 42 win 86"))
print(handle_command("tc stats"))
```

OpenClaw can keep using the original deterministic plan endpoints for fixture-based workflows, or call the new sync/scan endpoints when testing the cached live watchlist loop locally.

## Troubleshooting

Missing runtime directory:

- Set `TRADINGCLAW_DB_PATH` to the intended SQLite file.
- TradingClaw creates the parent directory automatically when opening the DB.

Bad fixture data:

- The file provider raises `ValueError` for malformed JSON or CSV fixtures.
- Verify `TRADINGCLAW_DATA_DIR` and the expected `mcl_*` / `m6e_*` files.

Missing Twelve Data API key:

- Set `TRADINGCLAW_TWELVEDATA_API_KEY` before using `/sync/run` or `tradingclaw-futures sync run`.
- The original file-backed `plan`, `setups`, and `reasoning-context` flows still work without it.

Webhook unset:

- Leave `TRADINGCLAW_WEBHOOK_URL=` blank for local-only mode.
- `POST /plan` still succeeds; the webhook result reports `"sent": false`.
- `POST /scan/run` still succeeds; the webhook result reports `"sent": false` or `"outside alert window"` depending on the request state.

Port already in use:

- Set a different `TRADINGCLAW_PORT`.
- Restart the server with the new value.

Negative PnL on CLI:

- Pass negative values as `--pnl-dollars=-22.5` to avoid shell ambiguity.

Live sync and scan:

- Run `POST /sync/run` before the first `POST /scan/run` so the SQLite cache has bars to analyze.
- If Twelve Data returns empty or unsupported `1min` data, TradingClaw falls back to `5min` and records the active interval in `/sync/status`.
- Sync and scan status are stored in SQLite `runtime_state`, so the latest summary survives process restarts.

OpenClaw reasoning handoff:

- If `TRADINGCLAW_OPENCLAW_ENABLED=true` but `TRADINGCLAW_OPENCLAW_REASONING_PATH` is blank, the bridge reports that reasoning is not configured and still prints the TradingClaw result.
- If the local OpenClaw gateway returns an error, TradingClaw and the bridge surface that error clearly without affecting journal state or scan persistence.

## Notes

- TradingClaw does not place orders.
- It does not include broker APIs.
- It does not include Tradovate integration.
- It does not run as a separate Discord bot.
- OpenClaw integration is external and optional.
