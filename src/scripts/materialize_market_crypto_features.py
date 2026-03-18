"""Materialize underlying crypto features aligned to each Polymarket market second.

This script builds a per-market, per-second feature table from:
  - market_outcomes
  - market_ticks
  - crypto_price_1s

Expected workflow:
  1. Import Binance 1-second bars with scripts.import_binance_1s
  2. Run this materializer
  3. Query the research view for backtests and feature exploration
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg

from shared.config import DB_CONFIG


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts.materialize_market_crypto_features",
        description="Build aligned per-market crypto feature table and research view.",
    )
    parser.add_argument(
        "--quote-asset",
        default="USDT",
        help="Quote asset to use when mapping assets to crypto symbols (default: USDT).",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Optional comma-separated asset filter, e.g. BTC,ETH,SOL.",
    )
    parser.add_argument(
        "--durations",
        default=None,
        help="Optional comma-separated duration filter in minutes, e.g. 5,15.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete existing feature rows for the selected markets before rebuilding.",
    )
    return parser.parse_args()


def parse_csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip().upper() for item in value.split(",") if item.strip()]
    return items or None


def parse_durations(value: str | None) -> list[int] | None:
    if not value:
        return None
    items = [int(item.strip()) for item in value.split(",") if item.strip()]
    return items or None


async def create_tables_and_view(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_crypto_features_1s (
            market_id                           TEXT             NOT NULL,
            elapsed_second                     INTEGER          NOT NULL,
            time                               TIMESTAMPTZ      NOT NULL,
            market_type                        TEXT             NOT NULL,
            asset                              TEXT             NOT NULL,
            quote_asset                        TEXT             NOT NULL,
            symbol                             TEXT             NOT NULL,
            total_seconds                      INTEGER          NOT NULL,
            market_up_price                    DOUBLE PRECISION,
            market_down_price                  DOUBLE PRECISION,
            market_up_price_market_open        DOUBLE PRECISION,
            market_up_delta_from_market_open   DOUBLE PRECISION,
            market_up_delta_5s                 DOUBLE PRECISION,
            market_up_delta_10s                DOUBLE PRECISION,
            market_up_delta_30s                DOUBLE PRECISION,
            underlying_bar_open                DOUBLE PRECISION,
            underlying_bar_high                DOUBLE PRECISION,
            underlying_bar_low                 DOUBLE PRECISION,
            underlying_close                   DOUBLE PRECISION,
            underlying_volume                  DOUBLE PRECISION,
            underlying_quote_volume            DOUBLE PRECISION,
            underlying_trade_count             INTEGER,
            underlying_taker_buy_base_volume   DOUBLE PRECISION,
            underlying_taker_buy_quote_volume  DOUBLE PRECISION,
            underlying_market_open_close       DOUBLE PRECISION,
            underlying_return_from_market_open DOUBLE PRECISION,
            underlying_return_5s               DOUBLE PRECISION,
            underlying_return_10s              DOUBLE PRECISION,
            underlying_return_30s              DOUBLE PRECISION,
            underlying_realized_vol_10s        DOUBLE PRECISION,
            underlying_realized_vol_30s        DOUBLE PRECISION,
            direction_mismatch_market_open     BOOLEAN,
            direction_mismatch_5s              BOOLEAN,
            direction_mismatch_10s             BOOLEAN,
            direction_mismatch_30s             BOOLEAN,
            created_at                         TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
            PRIMARY KEY (market_id, elapsed_second)
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_crypto_features_asset_second
        ON market_crypto_features_1s (asset, elapsed_second);
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_crypto_features_symbol_time
        ON market_crypto_features_1s (symbol, time);
        """
    )
    await conn.execute(
        """
        CREATE OR REPLACE VIEW vw_market_crypto_features_research AS
        SELECT
            market_id,
            market_type,
            asset,
            quote_asset,
            symbol,
            elapsed_second,
            time,
            total_seconds,
            market_up_price,
            market_down_price,
            market_up_price_market_open,
            market_up_delta_from_market_open,
            market_up_delta_5s,
            market_up_delta_10s,
            market_up_delta_30s,
            underlying_bar_open,
            underlying_bar_high,
            underlying_bar_low,
            underlying_close,
            underlying_volume,
            underlying_quote_volume,
            underlying_trade_count,
            underlying_taker_buy_base_volume,
            underlying_taker_buy_quote_volume,
            underlying_market_open_close,
            underlying_return_from_market_open,
            underlying_return_5s,
            underlying_return_10s,
            underlying_return_30s,
            underlying_realized_vol_10s,
            underlying_realized_vol_30s,
            direction_mismatch_market_open,
            direction_mismatch_5s,
            direction_mismatch_10s,
            direction_mismatch_30s
        FROM market_crypto_features_1s;
        """
    )


async def create_selected_markets(
    conn: asyncpg.Connection,
    quote_asset: str,
    assets: list[str] | None,
    durations: list[int] | None,
) -> int:
    filters = [
        "mo.resolved = TRUE",
        "mo.final_outcome IN ('Up', 'Down')",
        "mo.market_type ~* '^[A-Za-z0-9]+_[0-9]+m$'",
    ]
    params: list[object] = [quote_asset.upper()]
    placeholder_index = 2

    if assets:
        filters.append(
            f"UPPER(split_part(mo.market_type, '_', 1)) = ANY(${placeholder_index}::text[])"
        )
        params.append(assets)
        placeholder_index += 1

    if durations:
        filters.append(
            f"regexp_replace(split_part(mo.market_type, '_', 2), '[^0-9]', '', 'g')::int = ANY(${placeholder_index}::int[])"
        )
        params.append(durations)
        placeholder_index += 1

    await conn.execute("DROP TABLE IF EXISTS selected_markets;")
    query = f"""
        CREATE TEMP TABLE selected_markets AS
        WITH base AS (
            SELECT
                mo.market_id,
                mo.market_type,
                date_trunc('second', mo.started_at) AS started_at,
                date_trunc('second', COALESCE(
                    mo.ended_at,
                    mo.started_at + make_interval(
                        mins => regexp_replace(split_part(mo.market_type, '_', 2), '[^0-9]', '', 'g')::int
                    )
                )) AS ended_at,
                UPPER(split_part(mo.market_type, '_', 1)) AS asset,
                regexp_replace(split_part(mo.market_type, '_', 2), '[^0-9]', '', 'g')::int AS duration_minutes
            FROM market_outcomes mo
            WHERE {' AND '.join(filters)}
        )
        SELECT
            b.market_id,
            b.market_type,
            b.started_at,
            b.ended_at,
            b.asset,
            $1::text AS quote_asset,
            b.asset || $1::text AS symbol,
            b.duration_minutes,
            b.duration_minutes * 60 AS total_seconds
        FROM base b
        WHERE EXISTS (
            SELECT 1
            FROM crypto_price_1s cp
            WHERE cp.symbol = b.asset || $1::text
              AND cp.time >= b.started_at
              AND cp.time < b.started_at + make_interval(secs => b.duration_minutes * 60)
            LIMIT 1
        );
    """
    await conn.execute(query, *params)

    count = await conn.fetchval("SELECT COUNT(*) FROM selected_markets;")
    return int(count or 0)


async def refresh_selected_markets(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        DELETE FROM market_crypto_features_1s
        WHERE market_id IN (SELECT market_id FROM selected_markets);
        """
    )


async def materialize_features(conn: asyncpg.Connection) -> str:
    result = await conn.execute(
        """
        INSERT INTO market_crypto_features_1s (
            market_id,
            elapsed_second,
            time,
            market_type,
            asset,
            quote_asset,
            symbol,
            total_seconds,
            market_up_price,
            market_down_price,
            market_up_price_market_open,
            market_up_delta_from_market_open,
            market_up_delta_5s,
            market_up_delta_10s,
            market_up_delta_30s,
            underlying_bar_open,
            underlying_bar_high,
            underlying_bar_low,
            underlying_close,
            underlying_volume,
            underlying_quote_volume,
            underlying_trade_count,
            underlying_taker_buy_base_volume,
            underlying_taker_buy_quote_volume,
            underlying_market_open_close,
            underlying_return_from_market_open,
            underlying_return_5s,
            underlying_return_10s,
            underlying_return_30s,
            underlying_realized_vol_10s,
            underlying_realized_vol_30s,
            direction_mismatch_market_open,
            direction_mismatch_5s,
            direction_mismatch_10s,
            direction_mismatch_30s
        )
        WITH market_seconds AS (
            SELECT
                sm.market_id,
                sm.market_type,
                sm.asset,
                sm.quote_asset,
                sm.symbol,
                sm.started_at,
                sm.ended_at,
                sm.total_seconds,
                gs.elapsed_second,
                sm.started_at + make_interval(secs => gs.elapsed_second) AS feature_time
            FROM selected_markets sm
            CROSS JOIN LATERAL generate_series(0, sm.total_seconds - 1) AS gs(elapsed_second)
        ),
        market_tick_bucketed AS (
            SELECT
                sm.market_id,
                FLOOR(EXTRACT(EPOCH FROM (mt.time - sm.started_at)))::int AS elapsed_second,
                mt.time,
                mt.up_price::double precision AS market_up_price
            FROM selected_markets sm
            JOIN market_ticks mt
              ON mt.market_id = sm.market_id
            WHERE mt.time >= sm.started_at
              AND mt.time < sm.started_at + make_interval(secs => sm.total_seconds)
        ),
        market_tick_seconds AS (
            SELECT DISTINCT ON (market_id, elapsed_second)
                market_id,
                elapsed_second,
                market_up_price
            FROM market_tick_bucketed
            WHERE elapsed_second >= 0
            ORDER BY market_id, elapsed_second, time DESC
        ),
        joined AS (
            SELECT
                ms.market_id,
                ms.elapsed_second,
                ms.feature_time AS time,
                ms.market_type,
                ms.asset,
                ms.quote_asset,
                ms.symbol,
                ms.total_seconds,
                mts.market_up_price,
                CASE
                    WHEN mts.market_up_price IS NOT NULL THEN 1.0 - mts.market_up_price
                    ELSE NULL
                END AS market_down_price,
                cp.open AS underlying_bar_open,
                cp.high AS underlying_bar_high,
                cp.low AS underlying_bar_low,
                cp.close AS underlying_close,
                cp.volume AS underlying_volume,
                cp.quote_volume AS underlying_quote_volume,
                cp.trade_count AS underlying_trade_count,
                cp.taker_buy_base_volume AS underlying_taker_buy_base_volume,
                cp.taker_buy_quote_volume AS underlying_taker_buy_quote_volume
            FROM market_seconds ms
            LEFT JOIN market_tick_seconds mts
              ON mts.market_id = ms.market_id
             AND mts.elapsed_second = ms.elapsed_second
            LEFT JOIN crypto_price_1s cp
              ON cp.symbol = ms.symbol
             AND cp.time = ms.feature_time
        ),
        lagged AS (
            SELECT
                j.*,
                MAX(CASE WHEN j.elapsed_second = 0 THEN j.market_up_price END) OVER (
                    PARTITION BY j.market_id
                ) AS market_up_price_market_open,
                MAX(CASE WHEN j.elapsed_second = 0 THEN j.underlying_close END) OVER (
                    PARTITION BY j.market_id
                ) AS underlying_market_open_close,
                LAG(j.underlying_close, 5) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS underlying_close_5s_ago,
                LAG(j.underlying_close, 10) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS underlying_close_10s_ago,
                LAG(j.underlying_close, 30) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS underlying_close_30s_ago,
                LAG(j.market_up_price, 5) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS market_up_price_5s_ago,
                LAG(j.market_up_price, 10) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS market_up_price_10s_ago,
                LAG(j.market_up_price, 30) OVER (
                    PARTITION BY j.market_id
                    ORDER BY j.elapsed_second
                ) AS market_up_price_30s_ago,
                CASE
                    WHEN LAG(j.underlying_close) OVER (
                        PARTITION BY j.market_id
                        ORDER BY j.elapsed_second
                    ) > 0
                     AND j.underlying_close > 0
                    THEN LN(
                        j.underlying_close / LAG(j.underlying_close) OVER (
                            PARTITION BY j.market_id
                            ORDER BY j.elapsed_second
                        )
                    )
                    ELSE NULL
                END AS underlying_log_return_1s
            FROM joined j
        ),
        enriched AS (
            SELECT
                l.*,
                CASE
                    WHEN l.market_up_price_market_open IS NOT NULL AND l.market_up_price IS NOT NULL
                    THEN l.market_up_price - l.market_up_price_market_open
                    ELSE NULL
                END AS market_up_delta_from_market_open,
                CASE
                    WHEN l.market_up_price IS NOT NULL AND l.market_up_price_5s_ago IS NOT NULL
                    THEN l.market_up_price - l.market_up_price_5s_ago
                    ELSE NULL
                END AS market_up_delta_5s,
                CASE
                    WHEN l.market_up_price IS NOT NULL AND l.market_up_price_10s_ago IS NOT NULL
                    THEN l.market_up_price - l.market_up_price_10s_ago
                    ELSE NULL
                END AS market_up_delta_10s,
                CASE
                    WHEN l.market_up_price IS NOT NULL AND l.market_up_price_30s_ago IS NOT NULL
                    THEN l.market_up_price - l.market_up_price_30s_ago
                    ELSE NULL
                END AS market_up_delta_30s,
                CASE
                    WHEN l.underlying_market_open_close > 0 AND l.underlying_close > 0
                    THEN (l.underlying_close / l.underlying_market_open_close) - 1.0
                    ELSE NULL
                END AS underlying_return_from_market_open,
                CASE
                    WHEN l.underlying_close_5s_ago > 0 AND l.underlying_close > 0
                    THEN (l.underlying_close / l.underlying_close_5s_ago) - 1.0
                    ELSE NULL
                END AS underlying_return_5s,
                CASE
                    WHEN l.underlying_close_10s_ago > 0 AND l.underlying_close > 0
                    THEN (l.underlying_close / l.underlying_close_10s_ago) - 1.0
                    ELSE NULL
                END AS underlying_return_10s,
                CASE
                    WHEN l.underlying_close_30s_ago > 0 AND l.underlying_close > 0
                    THEN (l.underlying_close / l.underlying_close_30s_ago) - 1.0
                    ELSE NULL
                END AS underlying_return_30s,
                STDDEV_SAMP(l.underlying_log_return_1s) OVER (
                    PARTITION BY l.market_id
                    ORDER BY l.elapsed_second
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) AS underlying_realized_vol_10s,
                STDDEV_SAMP(l.underlying_log_return_1s) OVER (
                    PARTITION BY l.market_id
                    ORDER BY l.elapsed_second
                    ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ) AS underlying_realized_vol_30s
            FROM lagged l
        )
        SELECT
            e.market_id,
            e.elapsed_second,
            e.time,
            e.market_type,
            e.asset,
            e.quote_asset,
            e.symbol,
            e.total_seconds,
            e.market_up_price,
            e.market_down_price,
            e.market_up_price_market_open,
            e.market_up_delta_from_market_open,
            e.market_up_delta_5s,
            e.market_up_delta_10s,
            e.market_up_delta_30s,
            e.underlying_bar_open,
            e.underlying_bar_high,
            e.underlying_bar_low,
            e.underlying_close,
            e.underlying_volume,
            e.underlying_quote_volume,
            e.underlying_trade_count,
            e.underlying_taker_buy_base_volume,
            e.underlying_taker_buy_quote_volume,
            e.underlying_market_open_close,
            e.underlying_return_from_market_open,
            e.underlying_return_5s,
            e.underlying_return_10s,
            e.underlying_return_30s,
            e.underlying_realized_vol_10s,
            e.underlying_realized_vol_30s,
            CASE
                WHEN e.market_up_delta_from_market_open IS NULL
                  OR e.underlying_return_from_market_open IS NULL
                  OR ABS(e.market_up_delta_from_market_open) < 1e-12
                  OR ABS(e.underlying_return_from_market_open) < 1e-12
                THEN NULL
                ELSE SIGN(e.market_up_delta_from_market_open) <> SIGN(e.underlying_return_from_market_open)
            END AS direction_mismatch_market_open,
            CASE
                WHEN e.market_up_delta_5s IS NULL
                  OR e.underlying_return_5s IS NULL
                  OR ABS(e.market_up_delta_5s) < 1e-12
                  OR ABS(e.underlying_return_5s) < 1e-12
                THEN NULL
                ELSE SIGN(e.market_up_delta_5s) <> SIGN(e.underlying_return_5s)
            END AS direction_mismatch_5s,
            CASE
                WHEN e.market_up_delta_10s IS NULL
                  OR e.underlying_return_10s IS NULL
                  OR ABS(e.market_up_delta_10s) < 1e-12
                  OR ABS(e.underlying_return_10s) < 1e-12
                THEN NULL
                ELSE SIGN(e.market_up_delta_10s) <> SIGN(e.underlying_return_10s)
            END AS direction_mismatch_10s,
            CASE
                WHEN e.market_up_delta_30s IS NULL
                  OR e.underlying_return_30s IS NULL
                  OR ABS(e.market_up_delta_30s) < 1e-12
                  OR ABS(e.underlying_return_30s) < 1e-12
                THEN NULL
                ELSE SIGN(e.market_up_delta_30s) <> SIGN(e.underlying_return_30s)
            END AS direction_mismatch_30s
        FROM enriched e
        ON CONFLICT (market_id, elapsed_second) DO UPDATE SET
            time                               = EXCLUDED.time,
            market_type                        = EXCLUDED.market_type,
            asset                              = EXCLUDED.asset,
            quote_asset                        = EXCLUDED.quote_asset,
            symbol                             = EXCLUDED.symbol,
            total_seconds                      = EXCLUDED.total_seconds,
            market_up_price                    = EXCLUDED.market_up_price,
            market_down_price                  = EXCLUDED.market_down_price,
            market_up_price_market_open        = EXCLUDED.market_up_price_market_open,
            market_up_delta_from_market_open   = EXCLUDED.market_up_delta_from_market_open,
            market_up_delta_5s                 = EXCLUDED.market_up_delta_5s,
            market_up_delta_10s                = EXCLUDED.market_up_delta_10s,
            market_up_delta_30s                = EXCLUDED.market_up_delta_30s,
            underlying_bar_open                = EXCLUDED.underlying_bar_open,
            underlying_bar_high                = EXCLUDED.underlying_bar_high,
            underlying_bar_low                 = EXCLUDED.underlying_bar_low,
            underlying_close                   = EXCLUDED.underlying_close,
            underlying_volume                  = EXCLUDED.underlying_volume,
            underlying_quote_volume            = EXCLUDED.underlying_quote_volume,
            underlying_trade_count             = EXCLUDED.underlying_trade_count,
            underlying_taker_buy_base_volume   = EXCLUDED.underlying_taker_buy_base_volume,
            underlying_taker_buy_quote_volume  = EXCLUDED.underlying_taker_buy_quote_volume,
            underlying_market_open_close       = EXCLUDED.underlying_market_open_close,
            underlying_return_from_market_open = EXCLUDED.underlying_return_from_market_open,
            underlying_return_5s               = EXCLUDED.underlying_return_5s,
            underlying_return_10s              = EXCLUDED.underlying_return_10s,
            underlying_return_30s              = EXCLUDED.underlying_return_30s,
            underlying_realized_vol_10s        = EXCLUDED.underlying_realized_vol_10s,
            underlying_realized_vol_30s        = EXCLUDED.underlying_realized_vol_30s,
            direction_mismatch_market_open     = EXCLUDED.direction_mismatch_market_open,
            direction_mismatch_5s              = EXCLUDED.direction_mismatch_5s,
            direction_mismatch_10s             = EXCLUDED.direction_mismatch_10s,
            direction_mismatch_30s             = EXCLUDED.direction_mismatch_30s,
            created_at                         = NOW();
        """
    )
    return result


async def count_feature_rows(conn: asyncpg.Connection) -> int:
    count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM market_crypto_features_1s
        WHERE market_id IN (SELECT market_id FROM selected_markets);
        """
    )
    return int(count or 0)


async def main_async(args: argparse.Namespace) -> None:
    assets = parse_csv_list(args.assets)
    durations = parse_durations(args.durations)

    conn = await asyncpg.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )
    try:
        await create_tables_and_view(conn)
        market_count = await create_selected_markets(
            conn=conn,
            quote_asset=args.quote_asset,
            assets=assets,
            durations=durations,
        )

        if market_count == 0:
            print("No markets matched the requested filters with available crypto data.")
            return

        if args.refresh:
            await refresh_selected_markets(conn)

        result = await materialize_features(conn)
        feature_rows = await count_feature_rows(conn)

        print("Materialization complete")
        print(f"  Quote asset: {args.quote_asset.upper()}")
        print(f"  Markets selected: {market_count}")
        print(f"  Postgres result: {result}")
        print(f"  Feature rows now present for selected markets: {feature_rows}")
        print("  Research view: vw_market_crypto_features_research")
    finally:
        await conn.close()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
