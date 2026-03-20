# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PolyEdge Dash is a real-time analytics dashboard for Polymarket prediction market data. It tracks crypto asset price prediction markets (BTC, ETH, SOL, XRP) across 5-minute and 15-minute intervals, collecting tick-level pricing data and outcome results.

## Commands

```bash
pnpm dev          # Start dev server (http://localhost:3000)
pnpm build        # Production build
pnpm start        # Start production server
pnpm lint         # Run ESLint
```

No test framework is configured.

## Architecture

- **Framework**: Next.js 14 with App Router, TypeScript, Tailwind CSS
- **Output mode**: Standalone (for Docker deployment)
- **Package manager**: pnpm
- **UI**: shadcn/ui (Radix primitives) in `components/ui/`
- **Charts**: TradingView Lightweight Charts + Recharts
- **Database**: PostgreSQL via `pg` (connection pool in `lib/db.ts`)
- **Auth**: next-auth (session provider wraps the app in `layout.tsx`)
- **Fonts**: Geist Sans + Mono

### Data Flow

Server Components and API routes query PostgreSQL directly through `lib/db.ts` (a shared connection pool with 5s statement timeout). Query functions live in `lib/queries.ts` and domain-specific query files (`lib/calibration-queries.ts`, `lib/momentum-queries.ts`, etc.). The homepage uses `force-dynamic` + Suspense boundaries for streaming server-rendered sections.

Client components fetch data from `/api/*` routes via custom hooks in `hooks/` (notably `use-polling-fetch.ts` for auto-refresh).

### Key Database Tables

- `market_outcomes` — resolved market results (asset, interval, outcome, prices)
- `market_ticks` — tick-level price data (time series of "Up" prices 0.0–1.0)

### Route Structure

- `/` — Dashboard homepage (Server Component with Suspense streaming)
- `/markets` — Market browser with chart visualization
- `/analysis`, `/momentum-analytics`, `/bot`, `/control` — Feature pages
- `/strategy`, `/strategy2`, `/strategy3`, `/strategy4` — Strategy pages
- `/api/*` — ~20 API routes for data fetching and export

### Environment

Requires `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, and `POSTGRES_PORT`. Copy `.env.example` to `.env.local`.

## Standard Text Size Rules

| Element | Classes |
|---|---|
| Page titles (e.g. "PolyEdge", "Lab Analysis") | `text-2xl font-bold` |
| Section headers (e.g. "Markets", "Calibration Analysis") | `text-lg font-semibold` |
| Card titles (e.g. asset names like "Bitcoin", "BTC 5m") | `text-base font-semibold` |
| Table headers (`<th>`) | `text-xs font-semibold uppercase tracking-wider` |
| Table data (`<td>`) | `text-sm` |
| Badge/tag labels (e.g. "5m", "Live", "Strong") | `text-xs font-medium` |
| Metric values (large numbers in overview cards) | `text-2xl font-bold` |
| Metric labels (e.g. "RESOLVED", "TICKS") | `text-xs uppercase tracking-wider` |
| Chart axis labels | `text-xs` |
| Tooltip content | `text-xs` |
| Helper text / notes / descriptions | `text-xs text-muted-foreground` |
| Navigation links | `text-sm font-medium` |
| Button labels | `text-sm font-medium` |
| Input/filter labels | `text-sm` |
| Empty state messages | `text-sm text-muted-foreground` |
| Timestamps and secondary metadata | `text-xs text-muted-foreground` |

### Rules

- Never go below `text-xs` (12px) — anything smaller is unreadable
- Never use arbitrary pixel sizes — only use the Tailwind scale
- `text-sm` (14px) is the minimum for any content the user needs to read and act on, including all table data
- Consistency matters more than perfection — if two similar elements have different sizes, make them the same
