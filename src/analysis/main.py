#!/usr/bin/env python3
"""
PolyEdge Analysis — Full Statistical Analysis of Polymarket Data

Reads from market_ticks and market_outcomes (read-only),
writes results to dedicated analysis tables.

Usage:
    python -m analysis.main
    python -m analysis.main --dry-run
    python -m analysis.main --market-type btc_5m
"""

import argparse
import sys
import time
from datetime import timedelta

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values
from scipy.stats import binomtest

from shared.config import DB_CONFIG
from analysis.db_sync import get_connection
from analysis.constants import (
    CHECKPOINTS, PRICE_BUCKET_WIDTH, MIN_BUCKET_SAMPLES,
    MIN_TICKS_PER_MARKET, SIGNIFICANCE_LEVEL, to_python,
)

# ---------------------------------------------------------------------------
# DDL — analysis tables
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id SERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    markets_analyzed INT,
    ticks_analyzed BIGINT,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS calibration_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES analysis_runs(id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    checkpoint_seconds INT NOT NULL,
    price_bucket NUMERIC(4,2) NOT NULL,
    sample_count INT NOT NULL,
    up_wins INT NOT NULL,
    actual_win_rate NUMERIC(6,4) NOT NULL,
    expected_win_rate NUMERIC(6,4) NOT NULL,
    deviation NUMERIC(6,4) NOT NULL,
    p_value NUMERIC(8,6),
    significant BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS trajectory_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES analysis_runs(id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    checkpoint_seconds INT NOT NULL,
    outcome TEXT NOT NULL,
    avg_price NUMERIC(6,4) NOT NULL,
    std_price NUMERIC(6,4),
    sample_count INT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeofday_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES analysis_runs(id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    hour_utc INT NOT NULL,
    sample_count INT NOT NULL,
    up_wins INT NOT NULL,
    up_win_rate NUMERIC(6,4) NOT NULL,
    avg_price_range NUMERIC(6,4)
);

CREATE TABLE IF NOT EXISTS sequential_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES analysis_runs(id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    key TEXT NOT NULL,
    sample_count INT NOT NULL,
    up_win_rate NUMERIC(6,4) NOT NULL,
    notes TEXT
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_price_at_checkpoint(ticks_df, started_at, checkpoint_seconds):
    target = started_at + timedelta(seconds=checkpoint_seconds)
    diffs = (ticks_df['time'] - target).abs()
    idx = diffs.idxmin()
    if diffs.loc[idx].total_seconds() > 10:
        return np.nan
    return float(ticks_df.loc[idx, 'up_price'])


def window_seconds_for(market_type):
    if '15m' in str(market_type):
        return 900
    return 300


# ---------------------------------------------------------------------------
# Analysis functions (calibration, trajectory, time-of-day, sequential)
# ---------------------------------------------------------------------------

def run_calibration(df_outcomes, tick_dict, market_types, run_id, cursor, dry_run):
    all_rows = []
    summary = {'significant_count': 0, 'strongest': None}
    type_groups = list(market_types) + ['all']

    for mt in type_groups:
        markets = df_outcomes if mt == 'all' else df_outcomes[df_outcomes['market_type'] == mt]

        for cp in CHECKPOINTS:
            prices, outcomes = [], []
            for _, m in markets.iterrows():
                ticks = tick_dict.get(m['market_id'])
                if ticks is None or len(ticks) < MIN_TICKS_PER_MARKET:
                    continue
                p = get_price_at_checkpoint(ticks, m['started_at'], cp)
                if np.isnan(p):
                    continue
                prices.append(p)
                outcomes.append(1 if m['final_outcome'] == 'Up' else 0)

            if not prices:
                continue

            prices = np.array(prices)
            outcomes = np.array(outcomes)
            bucket_edges = np.arange(0, 1.001, PRICE_BUCKET_WIDTH)
            bucket_mids = (bucket_edges[:-1] + bucket_edges[1:]) / 2
            indices = np.clip(np.digitize(prices, bucket_edges) - 1, 0, len(bucket_mids) - 1)

            for bi, mid in enumerate(bucket_mids):
                mask = indices == bi
                n = int(mask.sum())
                if n < MIN_BUCKET_SAMPLES:
                    continue
                up_wins = int(outcomes[mask].sum())
                actual_wr = up_wins / n
                expected_wr = float(mid)
                deviation = actual_wr - expected_wr
                try:
                    pval = binomtest(up_wins, n, expected_wr).pvalue
                except ValueError:
                    pval = 1.0
                sig = pval < SIGNIFICANCE_LEVEL

                if sig:
                    summary['significant_count'] += 1
                    if summary['strongest'] is None or abs(deviation) > abs(summary['strongest']['deviation']):
                        summary['strongest'] = {
                            'market_type': mt, 'checkpoint': cp,
                            'bucket': round(mid, 3), 'deviation': round(deviation, 4),
                            'p_value': round(pval, 6),
                        }

                all_rows.append((
                    to_python(run_id), mt, to_python(cp), float(round(mid, 2)),
                    int(n), int(up_wins),
                    float(round(actual_wr, 4)), float(round(expected_wr, 4)),
                    float(round(deviation, 4)), float(round(pval, 6)), bool(sig),
                ))

    if not dry_run and all_rows:
        execute_values(cursor, """
            INSERT INTO calibration_results
                (run_id, market_type, checkpoint_seconds, price_bucket,
                 sample_count, up_wins, actual_win_rate, expected_win_rate,
                 deviation, p_value, significant)
            VALUES %s
        """, all_rows)

    return summary


def run_trajectory(df_outcomes, tick_dict, market_types, run_id, cursor, dry_run):
    traj_rows = []
    seq_rows = []
    summary = {'momentum_types': [], 'mean_reversion_count': 0}

    for mt in market_types:
        markets = df_outcomes[df_outcomes['market_type'] == mt]
        win_len = window_seconds_for(mt)

        for cp in CHECKPOINTS:
            for outcome in ('Up', 'Down'):
                subset = markets[markets['final_outcome'] == outcome]
                cp_prices = []
                for _, m in subset.iterrows():
                    ticks = tick_dict.get(m['market_id'])
                    if ticks is None or len(ticks) < MIN_TICKS_PER_MARKET:
                        continue
                    p = get_price_at_checkpoint(ticks, m['started_at'], cp)
                    if not np.isnan(p):
                        cp_prices.append(p)
                if not cp_prices:
                    continue
                traj_rows.append((
                    to_python(run_id), mt, to_python(cp), outcome,
                    float(round(np.mean(cp_prices), 4)),
                    float(round(np.std(cp_prices), 4)) if len(cp_prices) > 1 else 0.0,
                    int(len(cp_prices)),
                ))

        # Momentum effect
        rising_up = rising_total = falling_up = falling_total = 0
        for _, m in markets.iterrows():
            ticks = tick_dict.get(m['market_id'])
            if ticks is None or len(ticks) < MIN_TICKS_PER_MARKET:
                continue
            p30 = get_price_at_checkpoint(ticks, m['started_at'], 30)
            p60 = get_price_at_checkpoint(ticks, m['started_at'], 60)
            if np.isnan(p30) or np.isnan(p60):
                continue
            is_up = m['final_outcome'] == 'Up'
            if p60 > p30:
                rising_total += 1
                rising_up += int(is_up)
            elif p60 < p30:
                falling_total += 1
                falling_up += int(is_up)

        if rising_total >= MIN_BUCKET_SAMPLES:
            wr = rising_up / rising_total
            seq_rows.append((to_python(run_id), mt, 'momentum', 'rising_60s',
                             int(rising_total), float(round(wr, 4)),
                             f'Rising price 30s->60s: {wr:.1%} Up win rate'))
            if abs(wr - 0.5) > 0.04:
                summary['momentum_types'].append(mt)

        if falling_total >= MIN_BUCKET_SAMPLES:
            wr = falling_up / falling_total
            seq_rows.append((to_python(run_id), mt, 'momentum', 'falling_60s',
                             int(falling_total), float(round(wr, 4)),
                             f'Falling price 30s->60s: {wr:.1%} Up win rate'))

        # Mean reversion
        half_window = win_len / 2
        revert_up = revert_total = 0
        for _, m in markets.iterrows():
            ticks = tick_dict.get(m['market_id'])
            if ticks is None or len(ticks) < MIN_TICKS_PER_MARKET:
                continue
            elapsed = (ticks['time'] - m['started_at']).dt.total_seconds()
            first_half = ticks[(elapsed >= 0) & (elapsed <= half_window)]
            if first_half.empty:
                continue
            if first_half['up_price'].max() >= 0.65:
                after_peak_idx = first_half['up_price'].idxmax()
                after_peak = ticks.loc[after_peak_idx:]
                if (after_peak['up_price'] < 0.55).any():
                    revert_total += 1
                    revert_up += int(m['final_outcome'] == 'Up')

        if revert_total >= 5:
            wr = revert_up / revert_total
            seq_rows.append((to_python(run_id), mt, 'mean_reversion', 'peak_065_revert_055',
                             int(revert_total), float(round(wr, 4)),
                             f'Peaked >=0.65 then reverted <0.55: {wr:.1%} Up (n={revert_total})'))
            summary['mean_reversion_count'] += revert_total

    if not dry_run:
        if traj_rows:
            execute_values(cursor, """
                INSERT INTO trajectory_results
                    (run_id, market_type, checkpoint_seconds, outcome,
                     avg_price, std_price, sample_count)
                VALUES %s
            """, traj_rows)
        if seq_rows:
            execute_values(cursor, """
                INSERT INTO sequential_results
                    (run_id, market_type, analysis_type, key,
                     sample_count, up_win_rate, notes)
                VALUES %s
            """, seq_rows)

    return summary


def run_time_of_day(df_outcomes, tick_dict, market_types, run_id, cursor, dry_run):
    tod_rows = []
    summary = {'most_bullish': None, 'most_bearish': None}
    type_groups = list(market_types) + ['all']

    for mt in type_groups:
        markets = df_outcomes if mt == 'all' else df_outcomes[df_outcomes['market_type'] == mt]
        markets = markets.copy()
        markets['hour_utc'] = markets['started_at'].dt.hour

        price_ranges = {}
        for _, m in markets.iterrows():
            ticks = tick_dict.get(m['market_id'])
            if ticks is None or len(ticks) < MIN_TICKS_PER_MARKET:
                continue
            price_ranges[m['market_id']] = float(ticks['up_price'].max() - ticks['up_price'].min())

        markets['price_range'] = markets['market_id'].map(price_ranges)
        markets['is_up'] = (markets['final_outcome'] == 'Up').astype(int)

        for hour in range(24):
            hourly = markets[markets['hour_utc'] == hour]
            n = len(hourly)
            if n == 0:
                continue
            up_wins = int(hourly['is_up'].sum())
            wr = up_wins / n
            avg_range = float(hourly['price_range'].mean()) if hourly['price_range'].notna().any() else None

            tod_rows.append((
                to_python(run_id), mt, int(hour), int(n), int(up_wins),
                float(round(wr, 4)),
                float(round(avg_range, 4)) if avg_range is not None else None,
            ))

        if mt == 'all':
            hourly_stats = markets.groupby('hour_utc').agg(n=('is_up', 'size'), wr=('is_up', 'mean'))
            valid = hourly_stats[hourly_stats['n'] >= MIN_BUCKET_SAMPLES]
            if not valid.empty:
                best_hour = valid['wr'].idxmax()
                worst_hour = valid['wr'].idxmin()
                summary['most_bullish'] = (int(best_hour), round(float(valid.loc[best_hour, 'wr']), 4))
                summary['most_bearish'] = (int(worst_hour), round(float(valid.loc[worst_hour, 'wr']), 4))

    if not dry_run and tod_rows:
        execute_values(cursor, """
            INSERT INTO timeofday_results
                (run_id, market_type, hour_utc, sample_count,
                 up_wins, up_win_rate, avg_price_range)
            VALUES %s
        """, tod_rows)

    return summary


def run_sequential(df_outcomes, tick_dict, market_types, run_id, cursor, dry_run):
    seq_rows = []
    summary = {'strongest_streak': None, 'strongest_cross': None}

    for mt in market_types:
        markets = df_outcomes[df_outcomes['market_type'] == mt].sort_values('ended_at').reset_index(drop=True)
        outcomes_list = markets['final_outcome'].tolist()

        for streak_len in range(1, 6):
            patterns = {}
            for i in range(streak_len, len(outcomes_list)):
                prev = ''.join(o[0] for o in outcomes_list[i - streak_len:i])
                patterns.setdefault(prev, []).append(outcomes_list[i])

            for pattern, nexts in patterns.items():
                n = len(nexts)
                if n < 15:
                    continue
                up_wins = sum(1 for o in nexts if o == 'Up')
                wr = up_wins / n
                key = f'prev_{streak_len}_{pattern}'
                seq_rows.append((to_python(run_id), mt, 'streak', key, int(n),
                                 float(round(wr, 4)), f'After {pattern}: {wr:.1%} Up (n={n})'))
                if abs(wr - 0.5) > 0.08:
                    if summary['strongest_streak'] is None or abs(wr - 0.5) > abs(summary['strongest_streak']['wr'] - 0.5):
                        summary['strongest_streak'] = {'market_type': mt, 'key': key, 'wr': round(wr, 4), 'n': n}

    if not dry_run and seq_rows:
        execute_values(cursor, """
            INSERT INTO sequential_results
                (run_id, market_type, analysis_type, key,
                 sample_count, up_win_rate, notes)
            VALUES %s
        """, seq_rows)

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='PolyEdge Analysis — Full Analysis')
    parser.add_argument('--dry-run', action='store_true', help='Print results without writing to DB')
    parser.add_argument('--market-type', type=str, default=None, help='Analyse specific market type')
    args = parser.parse_args()

    t_start = time.time()
    print('[Analysis] Starting...')

    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        cursor.execute(DDL)
        conn.commit()

        market_type_filter = ""
        if args.market_type:
            market_type_filter = f" AND market_type = '{args.market_type}'"

        df_outcomes = pd.read_sql(f"""
            SELECT market_id, market_type, started_at, ended_at,
                   final_outcome, final_up_price
            FROM market_outcomes
            WHERE resolved = TRUE AND final_outcome IN ('Up', 'Down')
              {market_type_filter}
            ORDER BY started_at ASC
        """, conn, parse_dates=['started_at', 'ended_at'])

        if df_outcomes.empty:
            print('[Analysis] No resolved markets found. Exiting.')
            return

        market_ids = df_outcomes['market_id'].tolist()
        placeholders = ','.join(['%s'] * len(market_ids))
        df_ticks = pd.read_sql(f"""
            SELECT mt.time, mt.market_id, mt.up_price
            FROM market_ticks mt
            JOIN market_outcomes mo ON mt.market_id = mo.market_id
            WHERE mo.resolved = TRUE AND mo.final_outcome IN ('Up', 'Down')
              AND mt.market_id IN ({placeholders})
            ORDER BY mt.market_id, mt.time
        """, conn, params=market_ids, parse_dates=['time'])

        tick_dict = {}
        for mid, grp in df_ticks.groupby('market_id'):
            if len(grp) >= MIN_TICKS_PER_MARKET:
                tick_dict[mid] = grp.reset_index(drop=True)

        total_ticks = sum(len(t) for t in tick_dict.values())
        date_start = df_outcomes['started_at'].min()
        date_end = df_outcomes['ended_at'].max()
        market_types = sorted(df_outcomes['market_type'].dropna().unique())

        print(f'[Analysis] Loaded {len(df_outcomes)} resolved markets, {total_ticks} ticks')

        run_id = -1
        if not args.dry_run:
            notes = f'market_type={args.market_type}' if args.market_type else 'full run'
            cursor.execute("INSERT INTO analysis_runs (notes) VALUES (%s) RETURNING id", (notes,))
            run_id = cursor.fetchone()[0]

        cal_summary = run_calibration(df_outcomes, tick_dict, market_types, run_id, cursor, args.dry_run)
        traj_summary = run_trajectory(df_outcomes, tick_dict, market_types, run_id, cursor, args.dry_run)
        tod_summary = run_time_of_day(df_outcomes, tick_dict, market_types, run_id, cursor, args.dry_run)
        seq_summary = run_sequential(df_outcomes, tick_dict, market_types, run_id, cursor, args.dry_run)

        if not args.dry_run:
            cursor.execute("""
                UPDATE analysis_runs SET markets_analyzed=%s, ticks_analyzed=%s,
                    date_range_start=%s, date_range_end=%s WHERE id=%s
            """, (len(df_outcomes), total_ticks, date_start, date_end, run_id))
            conn.commit()

        duration = time.time() - t_start
        print(f'\n{"=" * 60}')
        print(f'POLYEDGE ANALYSIS — COMPLETE (run_id={run_id}, {duration:.1f}s)')
        print(f'{"=" * 60}')
        print(f'Markets: {len(df_outcomes)} | Ticks: {total_ticks}')
        print(f'Calibration significant deviations: {cal_summary["significant_count"]}')
        print(f'Momentum types: {", ".join(traj_summary["momentum_types"]) or "none"}')
        print(f'Mean reversion cases: {traj_summary["mean_reversion_count"]}')
        if tod_summary['most_bullish']:
            h, wr = tod_summary['most_bullish']
            print(f'Most bullish hour: {h} UTC ({wr:.1%})')
        if seq_summary['strongest_streak']:
            s = seq_summary['strongest_streak']
            print(f'Strongest streak: {s["key"]} -> {s["wr"]:.1%} (n={s["n"]})')

        # Run strategy backtests
        if not args.dry_run:
            from analysis.strategies.strategy_farming import run_farming_backtest
            run_farming_backtest(conn, run_id)

            from analysis.strategies.strategy_calibration import run_calibration_backtest
            run_calibration_backtest(conn, run_id)

            from analysis.strategies.strategy_momentum import run_momentum_backtest
            run_momentum_backtest(conn, run_id)

            from analysis.strategies.strategy_streak import run_streak_backtest
            run_streak_backtest(conn, run_id)

    except Exception as e:
        conn.rollback()
        print(f'[Analysis] ERROR: {e}', file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()
