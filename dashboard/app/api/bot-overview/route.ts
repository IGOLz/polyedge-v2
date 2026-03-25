export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

type OverallStats = {
  total_trades: string;
  wins: string;
  losses: string;
  pending: string;
  no_fills: string;
  skipped: string;
  total_pnl: string | null;
  total_bet: string | null;
  avg_pnl_per_trade: string | null;
};

type Last24hStats = {
  trades_24h: string;
  wins_24h: string;
  losses_24h: string;
  pnl_24h: string | null;
  bet_24h: string | null;
};

type YesterdayStats = {
  trades_yesterday: string;
  wins_yesterday: string;
  losses_yesterday: string;
  pnl_yesterday: string | null;
};

type StrategyStats = {
  strategy_name: string;
  trades: string;
  wins: string;
  losses: string;
  pnl: string | null;
  avg_pnl: string | null;
};

type DrawdownRow = {
  max_drawdown: string | null;
  current_drawdown: string | null;
  peak_pnl: string | null;
};

type StreakRow = {
  final_outcome: string | null;
};

type FrequencyRow = {
  first_trade_at: string | null;
  trading_days: string;
  total_resolved: string;
};

function computeStreak(rows: StreakRow[]): { type: string; length: number } {
  if (rows.length === 0) return { type: "none", length: 0 };
  const first = rows[0].final_outcome;
  if (!first) return { type: "none", length: 0 };
  const isWin = ["win_resolution", "take_profit"].includes(first);
  let length = 0;
  for (const row of rows) {
    const outcome = row.final_outcome;
    if (!outcome) break;
    const rowIsWin = ["win_resolution", "take_profit"].includes(outcome);
    if (rowIsWin === isWin) {
      length++;
    } else {
      break;
    }
  }
  return { type: isWin ? "win" : "loss", length };
}

async function fetchBotOverview() {
  try {
    const [overall, last24h, yesterday, strategyStats, drawdownRows, streakRows, frequencyRows] = await Promise.all([
      query<OverallStats>(`
        SELECT
          COUNT(*) FILTER (WHERE status = 'filled') as total_trades,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit')) as wins,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') as losses,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) as pending,
          COUNT(*) FILTER (WHERE status = 'fok_no_fill') as no_fills,
          COUNT(*) FILTER (WHERE status LIKE 'skipped%') as skipped,
          SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as total_pnl,
          SUM(bet_size_usd) FILTER (WHERE status = 'filled') as total_bet,
          AVG(${PNL_SQL}) FILTER (WHERE final_outcome IS NOT NULL) as avg_pnl_per_trade
        FROM bot_trades
      `),
      query<Last24hStats>(`
        SELECT
          COUNT(*) FILTER (WHERE status = 'filled') as trades_24h,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit')) as wins_24h,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') as losses_24h,
          SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as pnl_24h,
          SUM(bet_size_usd) FILTER (WHERE status = 'filled') as bet_24h
        FROM bot_trades
        WHERE placed_at > NOW() - INTERVAL '24 hours'
      `),
      query<YesterdayStats>(`
        SELECT
          COUNT(*) FILTER (WHERE status = 'filled') as trades_yesterday,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit')) as wins_yesterday,
          COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') as losses_yesterday,
          SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as pnl_yesterday
        FROM bot_trades
        WHERE placed_at > NOW() - INTERVAL '48 hours'
          AND placed_at <= NOW() - INTERVAL '24 hours'
      `),
      query<StrategyStats>(`
        SELECT
          strategy_name,
          COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as trades,
          COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit')) as wins,
          COUNT(*) FILTER (WHERE final_outcome IN ('loss','stop_loss')) as losses,
          SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as pnl,
          AVG(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as avg_pnl
        FROM bot_trades
        WHERE status = 'filled'
          AND strategy_name NOT LIKE 'momentum%'
        GROUP BY strategy_name
        ORDER BY SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) DESC NULLS LAST
      `),
      query<DrawdownRow>(`
        WITH cumulative AS (
          SELECT
            placed_at,
            SUM(${PNL_SQL}) OVER (ORDER BY placed_at) as running_pnl
          FROM bot_trades
          WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')
        ),
        with_peak AS (
          SELECT
            placed_at,
            running_pnl,
            MAX(running_pnl) OVER (ORDER BY placed_at) as peak
          FROM cumulative
        ),
        last_row AS (
          SELECT running_pnl - peak as current_drawdown
          FROM with_peak
          ORDER BY placed_at DESC
          LIMIT 1
        )
        SELECT
          MIN(running_pnl - peak) as max_drawdown,
          (SELECT current_drawdown FROM last_row) as current_drawdown,
          MAX(peak) as peak_pnl
        FROM with_peak
      `).catch(() => [] as DrawdownRow[]),
      query<StreakRow>(`
        SELECT final_outcome
        FROM bot_trades
        WHERE status = 'filled' AND final_outcome IN ('win_resolution','take_profit','loss','stop_loss')
        ORDER BY resolved_at DESC NULLS LAST, placed_at DESC
        LIMIT 50
      `),
      query<FrequencyRow>(`
        SELECT
          MIN(placed_at) as first_trade_at,
          COUNT(DISTINCT DATE(placed_at)) as trading_days,
          COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) as total_resolved
        FROM bot_trades
        WHERE status = 'filled'
      `),
    ]);

    const streak = computeStreak(streakRows);
    const freq = frequencyRows[0];
    const tradingDays = freq ? parseInt(freq.trading_days) : 0;
    const totalResolved = freq ? parseInt(freq.total_resolved) : 0;
    const tradesPerDay = tradingDays > 0 ? totalResolved / tradingDays : 0;

    // Drawdown: simpler fallback calculation
    let maxDrawdown = 0;
    let currentDrawdown = 0;
    if (drawdownRows.length > 0 && drawdownRows[0].max_drawdown != null) {
      maxDrawdown = parseFloat(drawdownRows[0].max_drawdown);
      currentDrawdown = parseFloat(drawdownRows[0].current_drawdown ?? "0");
    }

    return {
      overall: overall[0] || null,
      last24h: last24h[0] || null,
      yesterday: yesterday[0] || null,
      strategyStats: strategyStats.map((s) => ({
        strategy_name: s.strategy_name,
        trades: parseInt(s.trades),
        wins: parseInt(s.wins),
        losses: parseInt(s.losses),
        pnl: s.pnl != null ? parseFloat(s.pnl) : 0,
        avg_pnl: s.avg_pnl != null ? parseFloat(s.avg_pnl) : 0,
        win_rate: parseInt(s.trades) > 0
          ? (parseInt(s.wins) / parseInt(s.trades)) * 100
          : 0,
      })),
      drawdown: {
        max_drawdown: isNaN(maxDrawdown) ? 0 : maxDrawdown,
        current_drawdown: isNaN(currentDrawdown) ? 0 : currentDrawdown,
      },
      streak,
      tradesPerDay: parseFloat(tradesPerDay.toFixed(1)),
      firstTradeAt: freq?.first_trade_at || null,
    };
  } catch (error) {
    console.error("Failed to fetch bot overview:", error);
    return {
      overall: null, last24h: null, yesterday: null,
      strategyStats: [], drawdown: { max_drawdown: 0, current_drawdown: 0 },
      streak: { type: "none", length: 0 }, tradesPerDay: 0, firstTradeAt: null,
    };
  }
}

const getCachedBotOverview = unstable_cache(fetchBotOverview, ["bot-overview"], {
  revalidate: 60,
});

export async function GET() {
  try {
    const data = await getCachedBotOverview();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch bot overview:", error);
    return NextResponse.json(
      { overall: null, last24h: null, yesterday: null }
    );
  }
}
