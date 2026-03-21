# PolyEdge

Real-time analytics dashboard for [Polymarket](https://polymarket.com/) prediction market data. Tracks crypto asset price prediction markets (BTC, ETH, SOL, XRP) across 5-minute and 15-minute intervals, collecting tick-level pricing data and outcome results.

![Next.js](https://img.shields.io/badge/Next.js-14-black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38bdf8)

## Features

- **Dashboard Overview** — Total markets tracked, tick counts, days active, and collection start date
- **Market Cards** — Per-asset win rate breakdowns (24h and all-time) with live activity indicators
- **Market Browser** — Filter by asset and interval, browse resolved markets chronologically
- **Single Market Charts** — Price timeline visualization with outcome coloring (green/red/yellow)
- **Multi-Asset Charts** — Compare all assets within the same time window on a single chart
- **CSV Export** — Download tick data for individual markets or merged multi-asset datasets
- **JSON Export** — Full data dump of all overview stats, market outcomes, and tick rates
- **Auto-refresh** — Dashboard data revalidates every 60 seconds

## Tech Stack

- **Framework**: [Next.js 14](https://nextjs.org/) (App Router, Server Components + Client Components)
- **Language**: TypeScript
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) with custom dark theme
- **UI Components**: [shadcn/ui](https://ui.shadcn.com/) (Radix UI primitives)
- **Charts**: [Lightweight Charts](https://www.tradingview.com/lightweight-charts/) by TradingView
- **Database**: PostgreSQL via [node-postgres](https://node-postgres.com/)
- **Fonts**: [Geist](https://vercel.com/font) (Sans + Mono)

## Getting Started

### Prerequisites

- Node.js 18+
- PostgreSQL database with the required schema (see [Database Schema](#database-schema))

### Installation

```bash
git clone https://github.com/your-username/polyedge-dash.git
cd polyedge-dash
pnpm install
```

### Environment Variables

Copy the example env file and fill in your PostgreSQL connection settings:

```bash
cp .env.example .env.local
```

```env
POSTGRES_USER=polymarket
POSTGRES_PASSWORD=polymarket_secret
POSTGRES_DB=polymarket_tracker
POSTGRES_HOST=192.168.8.164
POSTGRES_PORT=5432
```

### Development

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

### Production Build

```bash
pnpm build
pnpm start
```

### Docker

```bash
docker build -t polyedge-dash .
docker run -p 3000:3000 \
  -e POSTGRES_USER=polymarket \
  -e POSTGRES_PASSWORD=polymarket_secret \
  -e POSTGRES_DB=polymarket_tracker \
  -e POSTGRES_HOST=192.168.8.164 \
  -e POSTGRES_PORT=5432 \
  polyedge-dash
```

## Database Schema

The dashboard expects two tables:

### `market_outcomes`

| Column          | Type      | Description                              |
|-----------------|-----------|------------------------------------------|
| `market_id`     | TEXT (PK) | Unique market identifier                 |
| `market_type`   | TEXT      | Asset + interval (e.g., `btc_5m`)        |
| `started_at`    | TIMESTAMP | Market open time                         |
| `ended_at`      | TIMESTAMP | Market close time                        |
| `final_outcome` | TEXT      | `Up`, `Down`, or `NULL`                  |
| `resolved`      | BOOLEAN   | Whether the market has been resolved     |
| `final_up_price`| NUMERIC   | Final "Up" price at resolution           |

### `market_ticks`

| Column        | Type      | Description                          |
|---------------|-----------|--------------------------------------|
| `market_id`   | TEXT (FK) | References `market_outcomes`         |
| `market_type` | TEXT      | Asset + interval                     |
| `time`        | TIMESTAMP | Tick timestamp                       |
| `up_price`    | NUMERIC   | "Up" outcome price (0.0 to 1.0)     |

## Project Structure

```
app/
  page.tsx                    # Dashboard homepage (Server Component)
  markets/page.tsx            # Market browser with charts (Client Component)
  api/
    markets/route.ts          # GET all markets with tick counts
    market-ticks/route.ts     # GET price ticks for a specific market
    tick-rate/route.ts        # GET tick activity rates by market type
    export/route.ts           # GET full JSON data export

components/
  navbar.tsx                  # Navigation bar with live UTC clock
  overview-cards.tsx          # Stats cards (markets, ticks, days, since)
  markets-grid.tsx            # Market type cards with win rates
  market-chart.tsx            # Single market price chart
  multi-market-chart.tsx      # Multi-asset comparison chart
  chart-header.tsx            # Shared chart header component
  filter-button.tsx           # Reusable filter toggle button
  loading-spinner.tsx         # Loading indicator
  download-button.tsx         # CSV/Export download button
  outcome-dot.tsx             # Outcome color indicator
  section-header.tsx          # Section title with divider
  ui/                         # shadcn/ui base components

hooks/
  use-live-clock.ts           # UTC clock with configurable interval
  use-market-ticks.ts         # Fetch tick data (single + multi)
  use-markets.ts              # Market filtering and selection state
  use-polling-fetch.ts        # Generic polling data fetcher

lib/
  db.ts                       # PostgreSQL connection pool
  queries.ts                  # Database query functions
  constants.ts                # Shared constants and config
  formatters.ts               # Date, number, and market formatting
  chart-config.ts             # Lightweight Charts configuration
  csv.ts                      # CSV export utilities
  utils.ts                    # Tailwind class merge utility

types/
  market.ts                   # Shared TypeScript interfaces
```

## License

MIT
