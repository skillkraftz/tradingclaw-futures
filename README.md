# openclaw-futures

`openclaw-futures` is a Discord-first futures setup engine for manual trade planning in `MCL` and `M6E`. It reads fixture-backed market data through pluggable providers, generates deterministic 1:3 setups, scores them, and renders account-aware trade plans for Discord slash commands.

## Scope

- Futures only: `MCL` and `M6E`
- Manual execution only
- Deterministic 1:3 reward-to-risk setup generation
- Account-aware contract sizing
- Discord slash commands via `discord.py` 2.x `app_commands`
- File-based market data provider for v1

## Package Layout

```text
src/openclaw_futures/
  bot.py
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
  render/
    discord_render.py
  discord/
    commands/
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
pytest
```

## Example Bot Run Command

```bash
DISCORD_BOT_TOKEN=your-token-here python -m openclaw_futures.bot
```

## Slash Commands

- `/trades <account_size>`
- `/setups`
- `/setups symbol:<MCL|M6E>`
- `/levels`
- `/account <account_size>`
- `/plan <account_size>`

## Data Fixtures

The default provider reads from `data/fixtures` inside the package root. JSON snapshots and CSV bar files are both supported.

Example files:

- `data/fixtures/mcl_snapshot.json`
- `data/fixtures/m6e_snapshot.json`
- `data/fixtures/mcl_bars.csv`
- `data/fixtures/m6e_bars.csv`

## Migration Note

### Removed from `morning-report`

- All EUR/USD and forex-specific logic
- All CL proxy wording and generic crude proxy behavior
- Report/watchlist/news pipelines
- Webhook posting flow
- Any assumption that setups are generated for non-futures instruments

### Preserved conceptually

- Deterministic 1:3 reward-to-risk setup engine
- Score-and-sort workflow for candidate setups
- Plain-text command-oriented output style

### New in `openclaw-futures`

- Discord-first command interface with slash commands
- Futures-native `MCL` and `M6E` contract modeling
- Account-aware contract sizing suggestions, including mixed allocations
- Pluggable market data providers with a file-backed v1 implementation
- Explicit daily risk caps, invalidation zones, and do-not-trade conditions

## Notes

- This package does not place orders.
- It does not include broker API integration.
- Market data is intentionally provider-driven so a live provider can be added later without changing setup or risk logic.
