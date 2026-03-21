import { query } from "./db";
import { MARKET_TYPES } from "./constants";

export async function getOverviewStats() {
  const [totalMarkets] = await query<{ count: string }>(
    "SELECT COUNT(*) as count FROM market_outcomes"
  );

  const [approxTicks] = await query<{ reltuples: number }>(
    "SELECT reltuples FROM pg_class WHERE relname = 'market_ticks'"
  );

  // reltuples is -1 when table hasn't been analyzed yet; fall back to a fast count
  let totalTicks = Math.round(approxTicks.reltuples);
  if (totalTicks < 0) {
    const [counted] = await query<{ count: string }>(
      "SELECT COUNT(*) as count FROM market_ticks WHERE time > NOW() - INTERVAL '24 hours'"
    );
    totalTicks = parseInt(counted.count);
  }

  const [startDate] = await query<{ min_start: string }>(
    "SELECT MIN(started_at) as min_start FROM market_outcomes"
  );

  return {
    totalMarkets: parseInt(totalMarkets.count),
    totalTicks,
    startDate: startDate.min_start,
    hoursCollected: startDate.min_start
      ? Math.round(
          (Date.now() - new Date(startDate.min_start).getTime()) /
            (1000 * 60 * 60)
        )
      : 0,
  };
}

export async function getMarketsByType() {
  const marketTypes = [...MARKET_TYPES];

  const outcomes = await query<{
    market_type: string;
    total: string;
    resolved: string;
    active: string;
    up_wins: string;
    down_wins: string;
    unknown_outcome: string;
  }>(`
    SELECT
      market_type,
      COUNT(*) as total,
      SUM(CASE WHEN resolved = TRUE THEN 1 ELSE 0 END) as resolved,
      SUM(CASE WHEN resolved = FALSE AND ended_at > NOW() THEN 1 ELSE 0 END) as active,
      SUM(CASE WHEN resolved = FALSE AND ended_at < NOW() THEN 1 ELSE 0 END) as unknown_outcome,
      SUM(CASE WHEN final_outcome = 'Up' THEN 1 ELSE 0 END) as up_wins,
      SUM(CASE WHEN final_outcome = 'Down' THEN 1 ELSE 0 END) as down_wins
    FROM market_outcomes
    GROUP BY market_type
    ORDER BY market_type
  `);

  const ticks = await query<{ market_type: string; tick_count: string }>(`
    SELECT market_type, COUNT(*) as tick_count
    FROM market_ticks
    WHERE time > NOW() - INTERVAL '24 hours'
    GROUP BY market_type
  `);

  const last24h = await query<{
    market_type: string;
    resolved_24h: string;
    up_wins_24h: string;
    down_wins_24h: string;
  }>(`
    SELECT
      market_type,
      COUNT(*) as resolved_24h,
      SUM(CASE WHEN final_outcome = 'Up' THEN 1 ELSE 0 END) as up_wins_24h,
      SUM(CASE WHEN final_outcome = 'Down' THEN 1 ELSE 0 END) as down_wins_24h
    FROM market_outcomes
    WHERE resolved = TRUE
      AND ended_at > NOW() - INTERVAL '24 hours'
      AND final_outcome IN ('Up', 'Down')
    GROUP BY market_type
  `);

  const tickMap = new Map(
    ticks.map((t) => [t.market_type, parseInt(t.tick_count)])
  );
  const last24hMap = new Map(last24h.map((r) => [r.market_type, r]));
  const outcomeMap = new Map(outcomes.map((o) => [o.market_type, o]));

  return marketTypes.map((type) => {
    const o = outcomeMap.get(type);
    const resolved = o ? parseInt(o.resolved) : 0;
    const upWins = o ? parseInt(o.up_wins) : 0;
    const downWins = o ? parseInt(o.down_wins) : 0;
    const unknownOutcome = o ? parseInt(o.unknown_outcome) : 0;
    const knownOutcomes = upWins + downWins;
    const winRate = knownOutcomes > 0 ? (upWins / knownOutcomes) * 100 : 0;

    const r24 = last24hMap.get(type);
    const upWins24h = r24 ? parseInt(r24.up_wins_24h) : 0;
    const downWins24h = r24 ? parseInt(r24.down_wins_24h) : 0;
    const known24h = upWins24h + downWins24h;
    const winRate24h = known24h > 0 ? (upWins24h / known24h) * 100 : 0;

    return {
      marketType: type,
      resolved,
      active: o ? parseInt(o.active) : 0,
      upWins,
      downWins,
      unknownOutcome,
      ticks24h: tickMap.get(type) || 0,
      upWinRate: winRate,
      upWinRate24h: winRate24h,
      resolved24h: known24h,
    };
  });
}

export async function getRecentActivity() {
  return query<{
    market_type: string;
    market_id: string;
    started_at: string;
    ended_at: string;
    final_outcome: string;
    final_up_price: string;
    tick_count: string;
  }>(`
    SELECT
      mo.market_type,
      mo.market_id,
      mo.started_at,
      mo.ended_at,
      mo.final_outcome,
      mo.final_up_price,
      COALESCE(tc.tick_count, 0) as tick_count
    FROM market_outcomes mo
    LEFT JOIN (
      SELECT market_id, COUNT(*) as tick_count
      FROM market_ticks
      WHERE time > NOW() - INTERVAL '24 hours'
      GROUP BY market_id
    ) tc ON mo.market_id = tc.market_id
    WHERE mo.resolved = true
    ORDER BY mo.ended_at DESC
    LIMIT 20
  `);
}

export async function getTickRates() {
  const rates = await query<{
    market_type: string;
    last_5m: string;
    last_15m: string;
    last_1h: string;
    last_24h: string;
  }>(`
    SELECT
      market_type,
      COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '5 minutes') as last_5m,
      COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '15 minutes') as last_15m,
      COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '1 hour') as last_1h,
      COUNT(*) as last_24h
    FROM market_ticks
    WHERE time > NOW() - INTERVAL '24 hours'
      AND market_type IS NOT NULL
    GROUP BY market_type
    ORDER BY market_type
  `);

  return rates.map((r) => ({
    marketType: r.market_type,
    last5m: parseInt(r.last_5m),
    last15m: parseInt(r.last_15m),
    last1h: parseInt(r.last_1h),
    last24h: parseInt(r.last_24h),
    collecting: parseInt(r.last_5m) > 0,
  }));
}

export async function getCalibrationData(secondsIntoWindow: number = 60) {
  const lowBound = secondsIntoWindow - 5;
  const highBound = secondsIntoWindow + 5;

  return query<{
    market_type: string;
    price_bucket: string;
    sample_count: string;
    up_win_rate: string;
  }>(`
    WITH tick_at_target AS (
      SELECT DISTINCT ON (mt.market_id)
        mt.market_id,
        mt.up_price,
        mo.final_outcome,
        mo.market_type
      FROM market_ticks mt
      JOIN market_outcomes mo ON mt.market_id = mo.market_id
      WHERE mo.resolved = TRUE
        AND mo.final_outcome IN ('Up', 'Down')
        AND EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN ${lowBound} AND ${highBound}
      ORDER BY mt.market_id, ABS(EXTRACT(EPOCH FROM (mt.time - mo.started_at)) - ${secondsIntoWindow})
    )
    SELECT
      market_type,
      ROUND(up_price * 20) / 20 AS price_bucket,
      COUNT(*) AS sample_count,
      ROUND(AVG((final_outcome = 'Up')::int::numeric) * 100, 1) AS up_win_rate
    FROM tick_at_target
    GROUP BY market_type, price_bucket
    ORDER BY market_type, price_bucket
  `);
}

export async function getCalibrationHeatmapData() {
  const timeOffsets = [30, 60, 90, 120, 150, 180, 240, 300];

  const rows = await query<{
    market_type: string;
    time_offset: string;
    price_bucket: string;
    sample_count: string;
    up_win_rate: string;
  }>(`
    WITH tick_snapshots AS (
      SELECT
        mt.market_id,
        mo.market_type,
        mo.final_outcome,
        mt.up_price,
        ROUND(EXTRACT(EPOCH FROM (mt.time - mo.started_at)))::int AS secs_in
      FROM market_ticks mt
      JOIN market_outcomes mo ON mt.market_id = mo.market_id
      WHERE mo.resolved = TRUE
        AND mo.final_outcome IN ('Up', 'Down')
        AND EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 25 AND 305
    ),
    bucketed AS (
      SELECT DISTINCT ON (market_id, time_bucket)
        market_id,
        market_type,
        final_outcome,
        up_price,
        CASE
          WHEN secs_in BETWEEN 25 AND 35 THEN 30
          WHEN secs_in BETWEEN 55 AND 65 THEN 60
          WHEN secs_in BETWEEN 85 AND 95 THEN 90
          WHEN secs_in BETWEEN 115 AND 125 THEN 120
          WHEN secs_in BETWEEN 145 AND 155 THEN 150
          WHEN secs_in BETWEEN 175 AND 185 THEN 180
          WHEN secs_in BETWEEN 235 AND 245 THEN 240
          WHEN secs_in BETWEEN 295 AND 305 THEN 300
        END AS time_bucket
      FROM tick_snapshots
      WHERE CASE
          WHEN secs_in BETWEEN 25 AND 35 THEN TRUE
          WHEN secs_in BETWEEN 55 AND 65 THEN TRUE
          WHEN secs_in BETWEEN 85 AND 95 THEN TRUE
          WHEN secs_in BETWEEN 115 AND 125 THEN TRUE
          WHEN secs_in BETWEEN 145 AND 155 THEN TRUE
          WHEN secs_in BETWEEN 175 AND 185 THEN TRUE
          WHEN secs_in BETWEEN 235 AND 245 THEN TRUE
          WHEN secs_in BETWEEN 295 AND 305 THEN TRUE
          ELSE FALSE
        END
      ORDER BY market_id, time_bucket, secs_in
    )
    SELECT
      market_type,
      time_bucket AS time_offset,
      ROUND(up_price * 20) / 20 AS price_bucket,
      COUNT(*) AS sample_count,
      ROUND(AVG((final_outcome = 'Up')::int::numeric) * 100, 1) AS up_win_rate
    FROM bucketed
    WHERE time_bucket IS NOT NULL
    GROUP BY market_type, time_bucket, ROUND(up_price * 20) / 20
    HAVING COUNT(*) >= 3
    ORDER BY market_type, time_bucket, price_bucket
  `);

  return rows;
}

export async function getEdgeScannerData() {
  // Historical edge scanner: find price buckets where actual win rate
  // deviates from implied probability (the price itself).
  // Edge = actual_win_rate - (price_bucket * 100)
  // e.g. price at 80¢ implies 80% Up, but historically wins 90% → +10% edge
  const rows = await query<{
    market_type: string;
    time_window: string;
    price_bucket: string;
    implied_prob: string;
    actual_win_rate: string;
    edge: string;
    sample_count: string;
    direction: string;
  }>(`
    WITH tick_at_times AS (
      SELECT DISTINCT ON (mt.market_id, time_bucket)
        mt.market_id,
        mo.market_type,
        mo.final_outcome,
        mt.up_price,
        CASE
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 25 AND 35 THEN 30
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 55 AND 65 THEN 60
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 115 AND 125 THEN 120
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 175 AND 185 THEN 180
        END AS time_bucket
      FROM market_ticks mt
      JOIN market_outcomes mo ON mt.market_id = mo.market_id
      WHERE mo.resolved = TRUE
        AND mo.final_outcome IN ('Up', 'Down')
        AND (
          EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 25 AND 35
          OR EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 55 AND 65
          OR EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 115 AND 125
          OR EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 175 AND 185
        )
      ORDER BY mt.market_id, time_bucket, ABS(EXTRACT(EPOCH FROM (mt.time - mo.started_at)) - CASE
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 25 AND 35 THEN 30
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 55 AND 65 THEN 60
          WHEN EXTRACT(EPOCH FROM (mt.time - mo.started_at)) BETWEEN 115 AND 125 THEN 120
          ELSE 180
        END)
    ),
    edges AS (
      SELECT
        market_type,
        time_bucket,
        ROUND(up_price * 20) / 20 AS price_bucket,
        ROUND(up_price * 20) / 20 * 100 AS implied_prob,
        ROUND(AVG((final_outcome = 'Up')::int::numeric) * 100, 1) AS actual_win_rate,
        ROUND(AVG((final_outcome = 'Up')::int::numeric) * 100, 1) - ROUND(up_price * 20) / 20 * 100 AS edge,
        COUNT(*) AS sample_count
      FROM tick_at_times
      WHERE time_bucket IS NOT NULL
      GROUP BY market_type, time_bucket, ROUND(up_price * 20) / 20
      HAVING COUNT(*) >= 10
    )
    SELECT
      market_type,
      time_bucket AS time_window,
      price_bucket,
      implied_prob,
      actual_win_rate,
      edge,
      sample_count,
      CASE WHEN edge > 0 THEN 'Up' ELSE 'Down' END AS direction
    FROM edges
    WHERE ABS(edge) >= 3
    ORDER BY ABS(edge) DESC
    LIMIT 30
  `);

  return rows;
}

export async function getTimeOfDayData() {
  const rows = await query<{
    market_type: string;
    hour_utc: string;
    total: string;
    up_wins: string;
    up_win_rate: string;
  }>(`
    SELECT
      market_type,
      EXTRACT(HOUR FROM started_at) AS hour_utc,
      COUNT(*) AS total,
      SUM(CASE WHEN final_outcome = 'Up' THEN 1 ELSE 0 END) AS up_wins,
      ROUND(AVG((final_outcome = 'Up')::int::numeric) * 100, 1) AS up_win_rate
    FROM market_outcomes
    WHERE resolved = TRUE AND final_outcome IN ('Up', 'Down')
    GROUP BY market_type, EXTRACT(HOUR FROM started_at)
    ORDER BY market_type, hour_utc
  `);

  return rows;
}

export async function getCrossAssetCorrelation() {
  // For markets that started at the same time with same interval, check outcome correlation
  const rows = await query<{
    asset_a: string;
    asset_b: string;
    interval: string;
    total_pairs: string;
    both_up: string;
    both_down: string;
    a_up_b_down: string;
    a_down_b_up: string;
    correlation_pct: string;
  }>(`
    WITH resolved_markets AS (
      SELECT
        market_type,
        SPLIT_PART(market_type, '_', 1) AS asset,
        SPLIT_PART(market_type, '_', 2) AS interval,
        started_at,
        final_outcome
      FROM market_outcomes
      WHERE resolved = TRUE AND final_outcome IN ('Up', 'Down')
    )
    SELECT
      a.asset AS asset_a,
      b.asset AS asset_b,
      a.interval,
      COUNT(*) AS total_pairs,
      SUM(CASE WHEN a.final_outcome = 'Up' AND b.final_outcome = 'Up' THEN 1 ELSE 0 END) AS both_up,
      SUM(CASE WHEN a.final_outcome = 'Down' AND b.final_outcome = 'Down' THEN 1 ELSE 0 END) AS both_down,
      SUM(CASE WHEN a.final_outcome = 'Up' AND b.final_outcome = 'Down' THEN 1 ELSE 0 END) AS a_up_b_down,
      SUM(CASE WHEN a.final_outcome = 'Down' AND b.final_outcome = 'Up' THEN 1 ELSE 0 END) AS a_down_b_up,
      ROUND(
        (SUM(CASE WHEN a.final_outcome = b.final_outcome THEN 1 ELSE 0 END)::numeric / COUNT(*)) * 100, 1
      ) AS correlation_pct
    FROM resolved_markets a
    JOIN resolved_markets b ON a.started_at = b.started_at
      AND a.interval = b.interval
      AND a.asset < b.asset
    GROUP BY a.asset, b.asset, a.interval
    HAVING COUNT(*) >= 10
    ORDER BY correlation_pct DESC
  `);

  return rows;
}

export async function getStreakData() {
  const rows = await query<{
    market_type: string;
    final_outcome: string;
    ended_at: string;
  }>(`
    SELECT market_type, final_outcome, ended_at
    FROM market_outcomes
    WHERE resolved = TRUE AND final_outcome IN ('Up', 'Down')
    ORDER BY market_type, ended_at DESC
  `);

  const grouped = new Map<string, { final_outcome: string; ended_at: string }[]>();
  for (const row of rows) {
    const list = grouped.get(row.market_type) || [];
    list.push(row);
    grouped.set(row.market_type, list);
  }

  return MARKET_TYPES.map((type) => {
    const markets = (grouped.get(type) || []).slice(0, 20);
    let streakLength = 0;
    let streakDirection = markets[0]?.final_outcome || "Up";

    for (const m of markets) {
      if (m.final_outcome === streakDirection) {
        streakLength++;
      } else {
        break;
      }
    }

    return {
      marketType: type,
      streakLength,
      streakDirection,
      lastTen: markets.slice(0, 10).map((m) => m.final_outcome),
    };
  });
}

// ---------------------------------------------------------------------------
// Analysis page — all data in one call
// ---------------------------------------------------------------------------

export async function getAnalysisData() {
  const runs = await query<{
    id: number;
    ran_at: string;
    markets_analyzed: number;
    total_ticks: number;
    date_range_start: string;
    date_range_end: string;
  }>("SELECT * FROM analysis_runs ORDER BY ran_at DESC LIMIT 1");

  if (runs.length === 0) {
    return {
      run: null,
      calibration: [],
      trajectory: [],
      timeofday: [],
      sequential: [],
      heatmap: [],
    };
  }

  const run = runs[0];
  const runId = run.id;

  const [calibration, trajectory, timeofday, sequential, heatmap] =
    await Promise.all([
      query<{
        run_id: number;
        market_type: string;
        checkpoint_seconds: number;
        price_bucket: number;
        sample_count: number;
        expected_win_rate: number;
        actual_win_rate: number;
        deviation: number;
        significant: boolean;
      }>(
        "SELECT * FROM calibration_results WHERE run_id = $1 ORDER BY market_type, checkpoint_seconds, price_bucket",
        [runId]
      ),
      query<{
        run_id: number;
        market_type: string;
        checkpoint_seconds: number;
        outcome: string;
        sample_count: number;
        win_rate: number;
        reversal_count: number;
        reversal_resolved_up_pct: number;
      }>(
        "SELECT * FROM trajectory_results WHERE run_id = $1 ORDER BY market_type, checkpoint_seconds, outcome",
        [runId]
      ),
      query<{
        run_id: number;
        market_type: string;
        hour_utc: number;
        sample_count: number;
        up_win_rate: number;
      }>(
        "SELECT * FROM timeofday_results WHERE run_id = $1 ORDER BY market_type, hour_utc",
        [runId]
      ),
      query<{
        run_id: number;
        market_type: string;
        analysis_type: string;
        key: string;
        sample_count: number;
        value: number;
        metadata: string;
      }>(
        "SELECT * FROM sequential_results WHERE run_id = $1 ORDER BY market_type, analysis_type, key",
        [runId]
      ),
      getCalibrationHeatmapData(),
    ]);

  return { run, calibration, trajectory, timeofday, sequential, heatmap };
}

