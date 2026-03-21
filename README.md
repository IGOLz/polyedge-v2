# PolyEdge

Unified Polymarket trading platform — data collection, strategy analysis, and live trading in a single monorepo.

## Architecture

```
src/
├── shared/          # Shared code used by ALL services
│   ├── config.py    # Central configuration (env vars, API endpoints)
│   ├── db.py        # Async database pool (asyncpg) + shared queries
│   ├── models.py    # Data models (MarketState, Tick)
│   ├── api.py       # Polymarket API calls (discovery, resolution, token IDs)
│   ├── ws.py        # WebSocket client for CLOB price feed
│   ├── http.py      # Proxy-aware HTTP client helpers
│   └── logging.py   # Logging setup
│
├── core/            # Data collector — runs 24/7, NEVER restart on updates
│   └── main.py      # Market discovery, WS listener, price recorder, resolution
│
├── analysis/        # Strategy research — run on-demand
│   ├── main.py      # Full statistical analysis pipeline
│   ├── constants.py # Analysis-specific constants
│   ├── db_sync.py   # Synchronous DB connection for pandas workloads
│   ├── strategies/  # Strategy backtests (momentum, calibration, streak, farming)
│   └── backtest/    # Backtesting framework (engine, data loader, modules)
│
└── trading/         # Live trading bot — can restart independently
    ├── main.py      # Bot main loop, outcome tracking, stop-loss monitoring
    ├── config.py    # Trading-specific config (auth, bet sizing)
    ├── constants.py # Strategy parameters (M3, M4, bet sizing, execution)
    ├── db.py        # Trading-specific tables (bot_trades, bot_logs, bot_config)
    ├── strategies.py # M3 (spike reversion) + M4 (volatility) strategies
    ├── executor.py  # 3-stage hybrid order execution
    ├── balance.py   # USDC balance checker
    ├── redeemer.py  # On-chain position redemption via Safe
    └── utils.py     # Colored logging for trading

dashboard/           # Next.js dashboard (analytics + limited DB controls)
├── app/             # App Router pages and API routes
├── components/      # UI building blocks and charts
├── lib/             # Database access + dashboard queries
└── package.json     # Dashboard scripts and dependencies
```

## Docker Services

| Service | Container | Purpose | Restarts |
|---------|-----------|---------|----------|
| `timescaledb` | polyedge-db | Shared PostgreSQL + TimescaleDB | Only if crashed |
| `core` | polyedge-core | Data collection (24/7) | **NEVER** on updates |
| `core-debug` | polyedge-core-debug | Dry-run validation, no DB writes | On-demand |
| `analysis` | polyedge-analysis | Strategy backtests | On-demand |
| `trading` | polyedge-trading | Live trading bot | Safe to restart |
| `dashboard` | polyedge-dashboard | Next.js UI for monitoring + light control actions | Safe to restart |

## Update Workflow (on LXC)

```bash
# Safe update — NEVER touches core
./update.sh

# Or manually:
git pull
docker compose build analysis trading
docker compose up -d analysis trading

# Core keeps running uninterrupted!
```

To update core (rare, planned):
```bash
./update.sh all
# or: docker compose build core && docker compose up -d core
```

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env
# Edit .env with your credentials

# 2. Start everything
docker compose up -d

# 3. Run analysis (one-time)
docker compose run --rm analysis

# 4. Open dashboard
open http://localhost:3000

# 5. Check status
docker compose ps
docker compose logs -f trading
```

### Historical Binance 1s Workflow

For the raw Binance 1-second import and feature-materialization workflow used by research backtests, see [src/docs/BINANCE_1S_IMPORT_WORKFLOW.md](src/docs/BINANCE_1S_IMPORT_WORKFLOW.md).

### Live Binance 1s Feed

`core` now also collects live Binance 1-second bars for `BTCUSDT`, `ETHUSDT`,
`SOLUSDT`, and `XRPUSDT`, stores them in `crypto_price_1s`, and backfills a
short startup/reconnect window before resuming the websocket stream.

`trading` does not call Binance directly. It reads raw bars from PostgreSQL and
builds the live crypto `feature_series` it needs in-process, so feature-driven
strategies such as `S13` and `S14` can run off the same DB-backed feed.

The historical import and feature materialization scripts still matter for
research and long-range backfills, but new live data no longer requires a
manual Binance import.

Dashboard auth uses `DASHBOARD_PASSWORD` and `NEXTAUTH_SECRET` from `.env`.
The dashboard connects to the same PostgreSQL database as the Python services.

### Trading Only With External Core/DB

If another project is already running `core` and writing live data to PostgreSQL,
you can run only the trading bot from this repo.

Set the external database host in `.env` or in the shell:

```bash
export POSTGRES_HOST=<external-db-host>
export POSTGRES_PORT=5432
```

Then start only trading without local dependencies:

```bash
docker compose up -d --no-deps trading
docker compose logs -f trading
```

This skips local `core`, `analysis`, and local `timescaledb`. The bot will use
the external database instead.

You can do the same for the dashboard by setting `POSTGRES_HOST` to the external
database host before starting `dashboard`.

## Core Modes

`core` is the production collector. It initializes the database, resumes unresolved markets from the database, writes `market_ticks` and `market_outcomes`, and continuously stores Binance 1-second bars in `crypto_price_1s`.

`core-debug` is a dry-run validator. It still runs discovery, websocket subscriptions, in-memory tick progression, market end detection, heartbeat logging, and resolution polling, but it never reads from or writes to PostgreSQL.

Use debug mode when the old collector is still running and writing to the database:

```bash
docker compose --profile debug up -d core-debug
docker compose logs -f core-debug
```

You should see logs confirming tracked markets, websocket subscriptions, heartbeat messages, debug tick checks, and market resolution checks, without any database writes.

When you're ready to promote this repo to the main collector, stop `core-debug` and run the normal `core` service instead.

## Key Design Decisions

1. **Core isolation**: Core's Docker image is built separately and never rebuilt during routine updates. Only `analysis`, `trading`, and `dashboard` are rebuilt/restarted.

2. **Shared database**: All services connect to the same TimescaleDB instance. Core writes `market_ticks` and `market_outcomes`; analysis reads them; trading reads them and writes to `bot_trades`; dashboard reads shared tables and exposes limited control flows.

3. **Shared code**: The `shared/` module contains database, API, WebSocket, and config code that's used by all Python services. The dashboard now lives in the same repo so UI changes can track backend strategy changes together.

4. **Independent deployability**: Each service has its own Dockerfile/runtime. Analysis, trading, and dashboard can be updated without affecting core's data collection.
