"""Shared asyncpg database pool — used by core and trading.

Usage:
    from shared.db import init_pool, get_pool, close_pool

The pool is initialised once; subsequent calls to get_pool() return
the same pool.  Tables are created on first init.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

import asyncpg

from shared.config import DB_CONFIG

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool(min_size: int = 2, max_size: int = 10, retries: int = 30) -> asyncpg.Pool:
    """Create the connection pool with retry loop (DB may still be starting)."""
    global _pool
    if _pool is not None:
        return _pool

    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                database=DB_CONFIG["database"],
                min_size=min_size,
                max_size=max_size,
            )
            logger.info("Database pool ready (%s@%s:%s/%s)",
                        DB_CONFIG["user"], DB_CONFIG["host"],
                        DB_CONFIG["port"], DB_CONFIG["database"])
            return _pool
        except Exception as exc:
            logger.error("DB connect attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt == retries:
                raise
            await asyncio.sleep(2)

    raise RuntimeError("Could not connect to database")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised — call init_pool() first")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Shared schema creation ──────────────────────────────────────────────

async def create_core_tables() -> None:
    """Create market_ticks and market_outcomes tables (owned by core)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_ticks (
                time        TIMESTAMPTZ     NOT NULL,
                market_id   TEXT            NOT NULL,
                up_price    NUMERIC(6,4)    NOT NULL,
                volume      NUMERIC(20,4),
                PRIMARY KEY (time, market_id)
            );
        """)
        await conn.execute("""
            SELECT create_hypertable('market_ticks', 'time', if_not_exists => TRUE);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_ticks_market_time
            ON market_ticks (market_id, time DESC);
        """)
        try:
            await conn.execute("""
                ALTER TABLE market_ticks SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'market_id'
                );
            """)
            await conn.execute("""
                SELECT add_compression_policy('market_ticks', INTERVAL '1 day',
                    if_not_exists => TRUE);
            """)
        except Exception:
            pass  # compression may already be configured or not supported

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_outcomes (
                market_id       TEXT            PRIMARY KEY,
                market_type     TEXT,
                started_at      TIMESTAMPTZ     NOT NULL,
                ended_at        TIMESTAMPTZ,
                final_outcome   TEXT,
                final_up_price  NUMERIC(6,4),
                total_volume    NUMERIC(20,4),
                resolved        BOOLEAN         DEFAULT FALSE
            );
        """)
    logger.info("Core database tables ready.")


# ── Shared tick/outcome queries ─────────────────────────────────────────

async def insert_tick(
    time: datetime,
    market_id: str,
    up_price: float,
    volume: Optional[float] = None,
) -> None:
    """Write a single price tick, ignoring duplicate PK conflicts."""
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO market_ticks (time, market_id, up_price, volume)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (time, market_id) DO UPDATE SET
                    up_price = EXCLUDED.up_price,
                    volume = COALESCE(EXCLUDED.volume, market_ticks.volume);
                """,
                time, market_id, up_price, volume,
            )
    except Exception as exc:
        logger.error("DB write failed — market %s: %s", market_id[:16], exc)


async def upsert_market_outcome(
    market_id: str,
    started_at: datetime,
    ended_at: Optional[datetime] = None,
    market_type: Optional[str] = None,
    final_outcome: Optional[str] = None,
    final_up_price: Optional[float] = None,
    total_volume: Optional[float] = None,
    resolved: bool = False,
) -> None:
    """Insert or update a row in market_outcomes."""
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO market_outcomes
                    (market_id, market_type, started_at, ended_at, final_outcome,
                     final_up_price, total_volume, resolved)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (market_id) DO UPDATE SET
                    market_type    = COALESCE(EXCLUDED.market_type,    market_outcomes.market_type),
                    ended_at       = COALESCE(EXCLUDED.ended_at,       market_outcomes.ended_at),
                    final_outcome  = COALESCE(EXCLUDED.final_outcome,  market_outcomes.final_outcome),
                    final_up_price = COALESCE(EXCLUDED.final_up_price, market_outcomes.final_up_price),
                    total_volume   = COALESCE(EXCLUDED.total_volume,   market_outcomes.total_volume),
                    resolved       = EXCLUDED.resolved;
                """,
                market_id, market_type, started_at, ended_at,
                final_outcome, final_up_price, total_volume, resolved,
            )
    except Exception as exc:
        logger.error("DB upsert failed — market %s: %s", market_id[:16], exc)


async def fetch_unresolved_markets() -> list[dict]:
    """Return all market_outcomes rows where resolved = FALSE."""
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT market_id, market_type, started_at, ended_at
                FROM market_outcomes
                WHERE resolved = FALSE;
                """
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("DB fetch unresolved markets failed: %s", exc)
        return []


async def get_active_markets() -> list[dict]:
    """Return markets whose ended_at is still in the future and not resolved."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT market_id, market_type, started_at, ended_at
            FROM market_outcomes
            WHERE ended_at > NOW()
              AND resolved = FALSE
            ORDER BY started_at ASC
        """)
    return [dict(r) for r in rows]


async def get_latest_price(market_id: str) -> Optional[float]:
    """Get most recent up_price for a market."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT up_price FROM market_ticks
            WHERE market_id = $1
            ORDER BY time DESC LIMIT 1
        """, market_id)
    return float(row["up_price"]) if row else None


async def get_price_at_second(market_id: str, started_at: datetime, seconds: int) -> Optional[float]:
    """Get up_price closest to `seconds` after market start (±10s window)."""
    from datetime import timedelta
    target = started_at + timedelta(seconds=seconds)
    window_start = target - timedelta(seconds=10)
    window_end = target + timedelta(seconds=10)

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT up_price
            FROM market_ticks
            WHERE market_id = $1
              AND time BETWEEN $2 AND $3
            ORDER BY ABS(EXTRACT(EPOCH FROM (time - $4)))
            LIMIT 1
        """, market_id, window_start, window_end, target)
    return float(row["up_price"]) if row else None


async def get_market_ticks(market_id: str, started_at: datetime, limit: int = 300) -> list[dict]:
    """Get all ticks for a market since start, ordered chronologically."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT market_id, time, up_price
            FROM market_ticks
            WHERE market_id = $1 AND time >= $2
            ORDER BY time ASC
            LIMIT $3
        """, market_id, started_at, limit)
    return [
        {
            "market_id": r["market_id"],
            "time": r["time"],
            "up_price": float(r["up_price"]),
            "down_price": round(1.0 - float(r["up_price"]), 6),
        }
        for r in rows
    ]
