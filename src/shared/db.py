"""Shared asyncpg database pool — used by core and trading.

Usage:
    from shared.db import init_pool, get_pool, close_pool

The pool is initialised once; subsequent calls to get_pool() return
the same pool.  Tables are created on first init.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import asyncpg

from shared.config import DB_CONFIG

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

_CRYPTO_BAR_FIELDS = (
    "symbol",
    "asset",
    "quote_asset",
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "source",
)


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
        await _create_crypto_tables_on_conn(conn)
        await _create_weather_tables_on_conn(conn)
    logger.info("Core database tables ready.")


async def create_crypto_tables(conn: asyncpg.Connection | None = None) -> None:
    """Create the shared crypto 1-second bar tables."""
    if conn is not None:
        await _create_crypto_tables_on_conn(conn)
        return

    pool = get_pool()
    async with pool.acquire() as pooled_conn:
        await _create_crypto_tables_on_conn(pooled_conn)


async def _create_crypto_tables_on_conn(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_price_1s (
            symbol                  TEXT             NOT NULL,
            asset                   TEXT             NOT NULL,
            quote_asset             TEXT             NOT NULL DEFAULT '',
            time                    TIMESTAMPTZ      NOT NULL,
            open                    DOUBLE PRECISION NOT NULL,
            high                    DOUBLE PRECISION NOT NULL,
            low                     DOUBLE PRECISION NOT NULL,
            close                   DOUBLE PRECISION NOT NULL,
            volume                  DOUBLE PRECISION NOT NULL,
            quote_volume            DOUBLE PRECISION NOT NULL,
            trade_count             INTEGER          NOT NULL,
            taker_buy_base_volume   DOUBLE PRECISION NOT NULL,
            taker_buy_quote_volume  DOUBLE PRECISION NOT NULL,
            source                  TEXT             NOT NULL DEFAULT 'binance',
            PRIMARY KEY (symbol, time)
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_price_1s_imports (
            file_name        TEXT            PRIMARY KEY,
            symbol           TEXT            NOT NULL,
            asset            TEXT            NOT NULL,
            quote_asset      TEXT            NOT NULL DEFAULT '',
            trading_day      DATE            NOT NULL,
            source_path      TEXT            NOT NULL,
            rows_loaded      INTEGER         NOT NULL,
            zero_trade_rows  INTEGER         NOT NULL,
            imported_at      TIMESTAMPTZ     NOT NULL
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_crypto_price_1s_asset_time
        ON crypto_price_1s (asset, time);
        """
    )
    try:
        await conn.execute(
            """
            SELECT create_hypertable('crypto_price_1s', 'time', if_not_exists => TRUE);
            """
        )
        await conn.execute(
            """
            ALTER TABLE crypto_price_1s SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol'
            );
            """
        )
        await conn.execute(
            """
            SELECT add_compression_policy('crypto_price_1s', INTERVAL '7 days', if_not_exists => TRUE);
            """
        )
    except Exception:
        pass


async def create_weather_tables(conn: asyncpg.Connection | None = None) -> None:
    """Create the shared weather pilot tables."""
    if conn is not None:
        await _create_weather_tables_on_conn(conn)
        return

    pool = get_pool()
    async with pool.acquire() as pooled_conn:
        await _create_weather_tables_on_conn(pooled_conn)


async def _create_weather_tables_on_conn(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_quotes (
            time            TIMESTAMPTZ      NOT NULL,
            market_id       TEXT             NOT NULL,
            outcome         TEXT             NOT NULL,
            asset_id        TEXT             NOT NULL,
            best_bid        DOUBLE PRECISION,
            best_ask        DOUBLE PRECISION,
            mid             DOUBLE PRECISION,
            best_bid_size   DOUBLE PRECISION,
            best_ask_size   DOUBLE PRECISION,
            source_event_type TEXT,
            PRIMARY KEY (time, market_id, outcome)
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_quotes_market_outcome_time
        ON market_quotes (market_id, outcome, time DESC);
        """
    )
    try:
        await conn.execute(
            """
            SELECT create_hypertable('market_quotes', 'time', if_not_exists => TRUE);
            """
        )
    except Exception:
        pass

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_station_map (
            city_key             TEXT PRIMARY KEY,
            city                 TEXT NOT NULL,
            station_code         TEXT,
            station_name         TEXT,
            lat                  DOUBLE PRECISION,
            lon                  DOUBLE PRECISION,
            timezone             TEXT NOT NULL,
            country_code         TEXT,
            observation_provider TEXT,
            forecast_provider    TEXT NOT NULL DEFAULT 'open_meteo',
            verified             BOOLEAN NOT NULL DEFAULT FALSE,
            notes                TEXT,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_market_catalog (
            market_id                 TEXT PRIMARY KEY,
            event_id                  TEXT NOT NULL,
            event_slug                TEXT NOT NULL,
            market_slug               TEXT NOT NULL DEFAULT '',
            question                  TEXT NOT NULL,
            city                      TEXT NOT NULL,
            city_key                  TEXT NOT NULL,
            station_code              TEXT,
            station_name              TEXT,
            lat                       DOUBLE PRECISION,
            lon                       DOUBLE PRECISION,
            timezone                  TEXT,
            local_date                DATE,
            metric                    TEXT NOT NULL,
            unit                      TEXT,
            bucket_label              TEXT,
            bucket_low                DOUBLE PRECISION,
            bucket_high               DOUBLE PRECISION,
            bucket_order              INTEGER NOT NULL DEFAULT 0,
            rule_family               TEXT,
            resolution_source_url     TEXT,
            resolution_precision_scale INTEGER NOT NULL DEFAULT 0,
            neg_risk                  BOOLEAN NOT NULL DEFAULT FALSE,
            active                    BOOLEAN NOT NULL DEFAULT TRUE,
            eligible                  BOOLEAN NOT NULL DEFAULT FALSE,
            eligibility_reason        TEXT,
            yes_token_id              TEXT,
            no_token_id               TEXT,
            started_at                TIMESTAMPTZ,
            ended_at                  TIMESTAMPTZ,
            last_discovered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weather_market_catalog_event_active
        ON weather_market_catalog (event_id, active, bucket_order);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weather_market_catalog_city_date
        ON weather_market_catalog (city_key, local_date DESC);
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_forecast_snapshots (
            id              BIGSERIAL PRIMARY KEY,
            captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            market_id       TEXT NOT NULL,
            provider        TEXT NOT NULL,
            model           TEXT NOT NULL,
            run_at          TIMESTAMPTZ NOT NULL,
            forecast_for    DATE,
            temp_max        DOUBLE PRECISION,
            temp_hourly     JSONB,
            cloud           JSONB,
            wind            JSONB,
            dewpoint        JSONB,
            precip_prob     JSONB,
            payload_json    JSONB
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weather_forecast_snapshots_lookup
        ON weather_forecast_snapshots (market_id, provider, model, run_at DESC);
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_observations (
            station_code    TEXT NOT NULL,
            observed_at     TIMESTAMPTZ NOT NULL,
            temperature     DOUBLE PRECISION,
            dewpoint        DOUBLE PRECISION,
            wind_speed      DOUBLE PRECISION,
            wind_direction  DOUBLE PRECISION,
            wind_gust       DOUBLE PRECISION,
            cloud           JSONB,
            visibility      TEXT,
            payload_json    JSONB,
            PRIMARY KEY (station_code, observed_at)
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_weather_observations_station_time
        ON weather_observations (station_code, observed_at DESC);
        """
    )


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


async def upsert_crypto_price_bar(bar: dict[str, Any]) -> None:
    """Insert or update a single 1-second crypto bar."""
    await upsert_crypto_price_bars([bar])


async def upsert_crypto_price_bars(bars: list[dict[str, Any]]) -> None:
    """Insert or update multiple 1-second crypto bars."""
    if not bars:
        return

    pool = get_pool()
    records = [
        tuple(bar[field] for field in _CRYPTO_BAR_FIELDS)
        for bar in bars
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO crypto_price_1s (
                symbol,
                asset,
                quote_asset,
                time,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count,
                taker_buy_base_volume,
                taker_buy_quote_volume,
                source
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14
            )
            ON CONFLICT (symbol, time) DO UPDATE SET
                asset = EXCLUDED.asset,
                quote_asset = EXCLUDED.quote_asset,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                quote_volume = EXCLUDED.quote_volume,
                trade_count = EXCLUDED.trade_count,
                taker_buy_base_volume = EXCLUDED.taker_buy_base_volume,
                taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume,
                source = EXCLUDED.source
            """,
            records,
        )


async def fetch_crypto_price_bars(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    """Fetch chronologically ordered crypto bars for ``symbol`` in a time range."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                symbol,
                asset,
                quote_asset,
                time,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count,
                taker_buy_base_volume,
                taker_buy_quote_volume,
                source
            FROM crypto_price_1s
            WHERE symbol = $1
              AND time BETWEEN $2 AND $3
            ORDER BY time ASC
            """,
            symbol.upper(),
            start_time,
            end_time,
        )
    return [dict(row) for row in rows]


async def get_latest_crypto_bar(symbol: str) -> dict[str, Any] | None:
    """Return the latest stored crypto bar for ``symbol``."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                symbol,
                asset,
                quote_asset,
                time,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count,
                taker_buy_base_volume,
                taker_buy_quote_volume,
                source
            FROM crypto_price_1s
            WHERE symbol = $1
            ORDER BY time DESC
            LIMIT 1
            """,
            symbol.upper(),
        )
    return dict(row) if row is not None else None


async def get_latest_crypto_bar_time(symbol: str) -> Optional[datetime]:
    """Return the latest stored crypto bar timestamp for ``symbol``."""
    latest = await get_latest_crypto_bar(symbol)
    if latest is None:
        return None
    return latest["time"]


async def insert_market_quotes(rows: list[dict[str, Any]]) -> None:
    """Insert append-only quote snapshots for market outcomes."""
    if not rows:
        return

    pool = get_pool()
    records = [
        (
            row["time"],
            row["market_id"],
            row["outcome"],
            row["asset_id"],
            row.get("best_bid"),
            row.get("best_ask"),
            row.get("mid"),
            row.get("best_bid_size"),
            row.get("best_ask_size"),
            row.get("source_event_type"),
        )
        for row in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO market_quotes (
                time,
                market_id,
                outcome,
                asset_id,
                best_bid,
                best_ask,
                mid,
                best_bid_size,
                best_ask_size,
                source_event_type
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (time, market_id, outcome) DO UPDATE SET
                asset_id = EXCLUDED.asset_id,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                mid = EXCLUDED.mid,
                best_bid_size = EXCLUDED.best_bid_size,
                best_ask_size = EXCLUDED.best_ask_size,
                source_event_type = EXCLUDED.source_event_type
            """,
            records,
        )


async def upsert_weather_station_map_rows(rows: list[dict[str, Any]]) -> None:
    """Upsert curated or discovered weather station mappings."""
    if not rows:
        return

    pool = get_pool()
    records = [
        (
            row["city_key"],
            row["city"],
            row.get("station_code"),
            row.get("station_name"),
            row.get("lat"),
            row.get("lon"),
            row["timezone"],
            row.get("country_code"),
            row.get("observation_provider"),
            row.get("forecast_provider", "open_meteo"),
            bool(row.get("verified", False)),
            row.get("notes"),
        )
        for row in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_station_map (
                city_key,
                city,
                station_code,
                station_name,
                lat,
                lon,
                timezone,
                country_code,
                observation_provider,
                forecast_provider,
                verified,
                notes
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT (city_key) DO UPDATE SET
                city = EXCLUDED.city,
                station_code = COALESCE(EXCLUDED.station_code, weather_station_map.station_code),
                station_name = COALESCE(EXCLUDED.station_name, weather_station_map.station_name),
                lat = COALESCE(EXCLUDED.lat, weather_station_map.lat),
                lon = COALESCE(EXCLUDED.lon, weather_station_map.lon),
                timezone = COALESCE(EXCLUDED.timezone, weather_station_map.timezone),
                country_code = COALESCE(EXCLUDED.country_code, weather_station_map.country_code),
                observation_provider = COALESCE(EXCLUDED.observation_provider, weather_station_map.observation_provider),
                forecast_provider = COALESCE(EXCLUDED.forecast_provider, weather_station_map.forecast_provider),
                verified = EXCLUDED.verified,
                notes = COALESCE(EXCLUDED.notes, weather_station_map.notes),
                updated_at = NOW()
            """,
            records,
        )


async def upsert_weather_market_catalog_rows(rows: list[dict[str, Any]]) -> None:
    """Upsert discovered weather market catalog rows."""
    if not rows:
        return

    pool = get_pool()
    records = [
        (
            row["market_id"],
            row["event_id"],
            row["event_slug"],
            row.get("market_slug", ""),
            row["question"],
            row["city"],
            row["city_key"],
            row.get("station_code"),
            row.get("station_name"),
            row.get("lat"),
            row.get("lon"),
            row.get("timezone"),
            row.get("local_date"),
            row.get("metric", "temperature_max"),
            row.get("unit"),
            row.get("bucket_label"),
            row.get("bucket_low"),
            row.get("bucket_high"),
            int(row.get("bucket_order", 0)),
            row.get("rule_family"),
            row.get("resolution_source_url"),
            int(row.get("resolution_precision_scale", 0)),
            bool(row.get("neg_risk", False)),
            bool(row.get("active", True)),
            bool(row.get("eligible", False)),
            row.get("eligibility_reason"),
            row.get("yes_token_id"),
            row.get("no_token_id"),
            row.get("started_at"),
            row.get("ended_at"),
        )
        for row in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_market_catalog (
                market_id,
                event_id,
                event_slug,
                market_slug,
                question,
                city,
                city_key,
                station_code,
                station_name,
                lat,
                lon,
                timezone,
                local_date,
                metric,
                unit,
                bucket_label,
                bucket_low,
                bucket_high,
                bucket_order,
                rule_family,
                resolution_source_url,
                resolution_precision_scale,
                neg_risk,
                active,
                eligible,
                eligibility_reason,
                yes_token_id,
                no_token_id,
                started_at,
                ended_at
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                $21,$22,$23,$24,$25,$26,$27,$28,$29,$30
            )
            ON CONFLICT (market_id) DO UPDATE SET
                event_id = EXCLUDED.event_id,
                event_slug = EXCLUDED.event_slug,
                market_slug = EXCLUDED.market_slug,
                question = EXCLUDED.question,
                city = EXCLUDED.city,
                city_key = EXCLUDED.city_key,
                station_code = COALESCE(EXCLUDED.station_code, weather_market_catalog.station_code),
                station_name = COALESCE(EXCLUDED.station_name, weather_market_catalog.station_name),
                lat = COALESCE(EXCLUDED.lat, weather_market_catalog.lat),
                lon = COALESCE(EXCLUDED.lon, weather_market_catalog.lon),
                timezone = COALESCE(EXCLUDED.timezone, weather_market_catalog.timezone),
                local_date = COALESCE(EXCLUDED.local_date, weather_market_catalog.local_date),
                metric = EXCLUDED.metric,
                unit = COALESCE(EXCLUDED.unit, weather_market_catalog.unit),
                bucket_label = EXCLUDED.bucket_label,
                bucket_low = EXCLUDED.bucket_low,
                bucket_high = EXCLUDED.bucket_high,
                bucket_order = EXCLUDED.bucket_order,
                rule_family = COALESCE(EXCLUDED.rule_family, weather_market_catalog.rule_family),
                resolution_source_url = COALESCE(EXCLUDED.resolution_source_url, weather_market_catalog.resolution_source_url),
                resolution_precision_scale = EXCLUDED.resolution_precision_scale,
                neg_risk = EXCLUDED.neg_risk,
                active = EXCLUDED.active,
                eligible = EXCLUDED.eligible,
                eligibility_reason = EXCLUDED.eligibility_reason,
                yes_token_id = COALESCE(EXCLUDED.yes_token_id, weather_market_catalog.yes_token_id),
                no_token_id = COALESCE(EXCLUDED.no_token_id, weather_market_catalog.no_token_id),
                started_at = COALESCE(EXCLUDED.started_at, weather_market_catalog.started_at),
                ended_at = COALESCE(EXCLUDED.ended_at, weather_market_catalog.ended_at),
                last_discovered_at = NOW()
            """,
            records,
        )


async def deactivate_missing_weather_markets(active_market_ids: list[str]) -> None:
    """Mark weather catalog rows inactive when they disappear from discovery."""
    pool = get_pool()
    async with pool.acquire() as conn:
        if active_market_ids:
            await conn.execute(
                """
                UPDATE weather_market_catalog
                SET active = FALSE
                WHERE metric = 'temperature_max'
                  AND market_id <> ALL($1::text[])
                """,
                active_market_ids,
            )
        else:
            await conn.execute(
                """
                UPDATE weather_market_catalog
                SET active = FALSE
                WHERE metric = 'temperature_max'
                """
            )


async def insert_weather_forecast_snapshots(rows: list[dict[str, Any]]) -> None:
    """Insert weather forecast snapshots."""
    if not rows:
        return

    pool = get_pool()
    records = [
        (
            row["market_id"],
            row["provider"],
            row["model"],
            row["run_at"],
            row.get("forecast_for"),
            row.get("temp_max"),
            json.dumps(row.get("temp_hourly")) if row.get("temp_hourly") is not None else None,
            json.dumps(row.get("cloud")) if row.get("cloud") is not None else None,
            json.dumps(row.get("wind")) if row.get("wind") is not None else None,
            json.dumps(row.get("dewpoint")) if row.get("dewpoint") is not None else None,
            json.dumps(row.get("precip_prob")) if row.get("precip_prob") is not None else None,
            json.dumps(row.get("payload_json")) if row.get("payload_json") is not None else None,
        )
        for row in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_forecast_snapshots (
                market_id,
                provider,
                model,
                run_at,
                forecast_for,
                temp_max,
                temp_hourly,
                cloud,
                wind,
                dewpoint,
                precip_prob,
                payload_json
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            records,
        )


async def upsert_weather_observations(rows: list[dict[str, Any]]) -> None:
    """Insert or update weather observations."""
    if not rows:
        return

    pool = get_pool()
    records = [
        (
            row["station_code"],
            row["observed_at"],
            row.get("temperature"),
            row.get("dewpoint"),
            row.get("wind_speed"),
            row.get("wind_direction"),
            row.get("wind_gust"),
            json.dumps(row.get("cloud")) if row.get("cloud") is not None else None,
            row.get("visibility"),
            json.dumps(row.get("payload_json")) if row.get("payload_json") is not None else None,
        )
        for row in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_observations (
                station_code,
                observed_at,
                temperature,
                dewpoint,
                wind_speed,
                wind_direction,
                wind_gust,
                cloud,
                visibility,
                payload_json
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (station_code, observed_at) DO UPDATE SET
                temperature = EXCLUDED.temperature,
                dewpoint = EXCLUDED.dewpoint,
                wind_speed = EXCLUDED.wind_speed,
                wind_direction = EXCLUDED.wind_direction,
                wind_gust = EXCLUDED.wind_gust,
                cloud = EXCLUDED.cloud,
                visibility = EXCLUDED.visibility,
                payload_json = EXCLUDED.payload_json
            """,
            records,
        )
