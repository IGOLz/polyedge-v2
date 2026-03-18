"""
Data loader for backtesting framework.
Efficiently loads market data and ticks from PostgreSQL into memory.
"""

import asyncio
import asyncpg
import numpy as np
from collections import defaultdict

from shared.config import DB_CONFIG

CRYPTO_FEATURE_COLUMNS = [
    "market_up_price_market_open",
    "market_up_delta_from_market_open",
    "market_up_delta_5s",
    "market_up_delta_10s",
    "market_up_delta_30s",
    "underlying_bar_open",
    "underlying_bar_high",
    "underlying_bar_low",
    "underlying_close",
    "underlying_volume",
    "underlying_quote_volume",
    "underlying_trade_count",
    "underlying_taker_buy_base_volume",
    "underlying_taker_buy_quote_volume",
    "underlying_market_open_close",
    "underlying_return_from_market_open",
    "underlying_return_5s",
    "underlying_return_10s",
    "underlying_return_30s",
    "underlying_realized_vol_10s",
    "underlying_realized_vol_30s",
    "direction_mismatch_market_open",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
]

BOOL_FEATURE_COLUMNS = {
    "direction_mismatch_market_open",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
}


async def _load_from_db():
    """Load all resolved markets and ticks from database."""
    conn = await asyncpg.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
    )

    try:
        print("Loading resolved markets...")
        market_rows = await conn.fetch("""
            SELECT market_id, market_type, started_at, ended_at, final_outcome
            FROM market_outcomes
            WHERE resolved = TRUE
              AND UPPER(final_outcome) IN ('UP', 'DOWN')
            ORDER BY started_at
        """)

        markets_raw = [dict(r) for r in market_rows]
        for market in markets_raw:
            outcome = (market.get("final_outcome") or "").upper()
            market["final_outcome"] = "Up" if outcome == "UP" else "Down"
        print(f"  Found {len(markets_raw)} resolved markets")

        if not markets_raw:
            return [], defaultdict(list), defaultdict(list)

        market_ids = [m['market_id'] for m in markets_raw]

        print("Loading ticks...")
        tick_rows = await conn.fetch("""
            SELECT market_id, time, up_price
            FROM market_ticks
            WHERE market_id = ANY($1)
            ORDER BY time
        """, market_ids)

        ticks_by_market = defaultdict(list)
        for r in tick_rows:
            ticks_by_market[r['market_id']].append({
                'time': r['time'],
                'up_price': float(r['up_price']),
            })

        print(f"  Loaded {len(tick_rows)} ticks across {len(ticks_by_market)} markets")

        feature_rows_by_market = defaultdict(list)
        feature_table_exists = await conn.fetchval(
            "SELECT to_regclass('public.market_crypto_features_1s') IS NOT NULL;"
        )

        if feature_table_exists:
            print("Loading aligned crypto features...")
            feature_columns_sql = ", ".join(CRYPTO_FEATURE_COLUMNS)
            feature_rows = await conn.fetch(
                f"""
                SELECT market_id, elapsed_second, {feature_columns_sql}
                FROM market_crypto_features_1s
                WHERE market_id = ANY($1)
                ORDER BY market_id, elapsed_second
                """,
                market_ids,
            )

            for row in feature_rows:
                feature_rows_by_market[row["market_id"]].append(dict(row))

            print(
                f"  Loaded {len(feature_rows)} feature rows across "
                f"{len(feature_rows_by_market)} markets"
            )

    finally:
        await conn.close()

    return markets_raw, ticks_by_market, feature_rows_by_market


def _build_feature_series(feature_rows, total_seconds):
    if not feature_rows:
        return {}

    feature_series = {
        column: np.full(total_seconds, np.nan)
        for column in CRYPTO_FEATURE_COLUMNS
    }

    for row in feature_rows:
        second = int(row["elapsed_second"])
        if second < 0 or second >= total_seconds:
            continue

        for column in CRYPTO_FEATURE_COLUMNS:
            value = row.get(column)
            if value is None:
                continue
            if column in BOOL_FEATURE_COLUMNS:
                feature_series[column][second] = 1.0 if value else 0.0
            else:
                feature_series[column][second] = float(value)

    return feature_series


def _annotate_streak_metadata(markets):
    streak_state = {}
    resolved_markets = sorted(markets, key=lambda m: m['ended_at'] or m['started_at'])
    resolved_idx = 0

    for market in sorted(markets, key=lambda m: m['started_at']):
        market_start = market['started_at']

        while resolved_idx < len(resolved_markets):
            resolved_market = resolved_markets[resolved_idx]
            resolved_time = resolved_market['ended_at'] or resolved_market['started_at']
            if resolved_time is None or resolved_time > market_start:
                break

            market_type = resolved_market['market_type']
            outcome = resolved_market['final_outcome']
            prior_direction, prior_length = streak_state.get(market_type, (None, 0))
            if outcome == prior_direction:
                streak_state[market_type] = (outcome, prior_length + 1)
            else:
                streak_state[market_type] = (outcome, 1)
            resolved_idx += 1

        prior_direction, prior_length = streak_state.get(market['market_type'], (None, 0))
        market['prior_market_type_streak_direction'] = prior_direction
        market['prior_market_type_streak_length'] = prior_length


def load_all_data():
    """
    Load all resolved markets with tick data.
    Returns list of market dicts, each containing:
      - market_id, market_type, asset, duration_minutes, total_seconds
      - started_at, ended_at, final_outcome, hour
      - ticks: numpy array indexed by second (NaN for missing)
    """
    markets_raw, ticks_by_market, feature_rows_by_market = asyncio.run(_load_from_db())

    if not markets_raw:
        print("No resolved markets found.")
        return []

    markets = []
    for m in markets_raw:
        mid = m['market_id']
        raw_ticks = ticks_by_market.get(mid, [])
        if len(raw_ticks) < 10:
            continue

        market_type = m.get('market_type')
        if not market_type or '_' not in market_type:
            continue

        parts = market_type.split('_')
        if len(parts) != 2:
            continue

        asset = parts[0]
        try:
            duration_minutes = int(parts[1].replace('m', ''))
        except ValueError:
            continue
        total_seconds = duration_minutes * 60

        # Build tick array indexed by elapsed second
        tick_array = np.full(total_seconds, np.nan)
        started_at = m['started_at']
        for t in raw_ticks:
            elapsed = int((t['time'] - started_at).total_seconds())
            if 0 <= elapsed < total_seconds:
                tick_array[elapsed] = t['up_price']

        markets.append({
            'market_id': mid,
            'market_type': market_type,
            'asset': asset,
            'duration_minutes': duration_minutes,
            'total_seconds': total_seconds,
            'started_at': started_at,
            'ended_at': m['ended_at'],
            'final_outcome': m['final_outcome'],
            'hour': started_at.hour,
            'prices': tick_array,
            'feature_series': _build_feature_series(
                feature_rows_by_market.get(mid, []),
                total_seconds,
            ),
        })

    _annotate_streak_metadata(markets)

    print(f"Processed {len(markets)} markets with sufficient tick data")

    # Print summary
    assets = defaultdict(int)
    durations = defaultdict(int)
    for m in markets:
        assets[m['asset']] += 1
        durations[m['duration_minutes']] += 1

    print(f"\nDataset summary:")
    for asset, count in sorted(assets.items()):
        print(f"  {asset}: {count} markets")
    for dur, count in sorted(durations.items()):
        print(f"  {dur}m: {count} markets")

    date_range_start = min(m['started_at'] for m in markets)
    date_range_end = max(m['ended_at'] for m in markets)
    days = (date_range_end - date_range_start).total_seconds() / 86400
    print(f"  Date range: {date_range_start} to {date_range_end}")
    print(f"  Duration: {days:.1f} days\n")

    return markets


def get_price_at_second(tick_array, target_sec, tolerance=5):
    """Get up_price at target second, or nearest within +/- tolerance."""
    if 0 <= target_sec < len(tick_array):
        price = tick_array[target_sec]
        if not np.isnan(price):
            return float(price)
    for offset in range(1, tolerance + 1):
        for s in [target_sec + offset, target_sec - offset]:
            if 0 <= s < len(tick_array):
                price = tick_array[s]
                if not np.isnan(price):
                    return float(price)
    return None


def filter_markets(markets, assets=None, durations=None):
    """Filter markets by asset list and/or duration list."""
    result = markets
    if assets:
        result = [m for m in result if m['asset'] in assets]
    if durations:
        result = [m for m in result if m['duration_minutes'] in durations]
    return result
