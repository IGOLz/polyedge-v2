import "server-only";

import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

/**
 * CTE that unions bot_trades with weather_clone_positions so the dashboard
 * shows data from both trading systems.  Weather positions are mapped to the
 * same column set used by the metrics queries (pnl_calc replaces inline PNL_SQL).
 */
const ALL_TRADES_CTE = `all_trades AS (
  SELECT
    placed_at,
    resolved_at,
    status,
    final_outcome,
    (${PNL_SQL}) AS pnl_calc,
    strategy_name,
    market_type
  FROM bot_trades
  UNION ALL
  SELECT
    opened_at        AS placed_at,
    closed_at        AS resolved_at,
    'filled'::text   AS status,
    CASE
      WHEN wcp.status = 'redeemed_closed'
           AND realized_exit_value_usd >= total_entry_cost THEN 'take_profit'
      WHEN wcp.status = 'redeemed_closed' THEN 'loss'
      ELSE NULL
    END              AS final_outcome,
    CASE
      WHEN wcp.status = 'redeemed_closed'
        THEN realized_exit_value_usd - total_entry_cost
      ELSE NULL
    END              AS pnl_calc,
    strategy_name,
    city || ' ' || bucket_label AS market_type
  FROM weather_clone_positions wcp
  WHERE NOT shadow_only
    AND wcp.status IN ('open_directional', 'redeemed_closed')
    AND total_entry_cost > 0
)`;

export interface BotOverviewMetrics {
  resolvedTrades: number;
  wins: number;
  losses: number;
  takeProfits: number;
  heldToExpiryLosses: number;
  stopLosses: number;
  openTrades: number;
  totalPnl: number;
  avgPnlPerTrade: number;
  profitFactor: number | null;
  lastTradeAt: string | null;
}

export interface BotWindowMetrics {
  trades: number;
  wins: number;
  losses: number;
  takeProfits: number;
  heldToExpiryLosses: number;
  stopLosses: number;
  openTrades: number;
  totalPnl: number;
  avgPnlPerTrade: number;
  profitFactor: number | null;
}

export interface BotActivityPoint {
  hour: string;
  trades: number;
  wins: number;
  pnl: number;
}

export interface RecentTradeRow {
  id: string;
  marketType: string;
  strategyName: string;
  side: string;
  entryPrice: number;
  exitPrice: number | null;
  betSize: number;
  pnl: number | null;
  placedAt: string;
  resolvedAt: string | null;
  status: string;
  finalOutcome: string | null;
}

export interface BotStrategyMetrics {
  strategyName: string;
  trades: number;
  wins: number;
  losses: number;
  pnl: number;
  avgPnl: number;
  winRate: number;
}

export interface BotDrawdownMetrics {
  maxDrawdown: number;
  currentDrawdown: number;
}

export interface BotStreakMetrics {
  type: string;
  length: number;
}

export interface BotDashboardData {
  connected: boolean;
  error: string | null;
  overall: BotOverviewMetrics | null;
  last24Hours: BotWindowMetrics | null;
  previous24Hours: BotWindowMetrics | null;
  activity24Hours: BotActivityPoint[];
  recentTrades: RecentTradeRow[];
  strategyBreakdown: BotStrategyMetrics[];
  drawdown: BotDrawdownMetrics;
  streak: BotStreakMetrics;
  tradesPerDay: number;
}

type OverviewRow = {
  resolved_trades: string;
  wins: string;
  losses: string;
  take_profits: string;
  held_to_expiry_losses: string;
  stop_losses: string;
  open_trades: string;
  total_pnl: string | null;
  avg_pnl_per_trade: string | null;
  gross_profit: string | null;
  gross_loss: string | null;
  last_trade_at: string | null;
};

type HourlyRow = {
  hour_bucket: string;
  trades: string;
  wins: string;
  pnl: string | null;
};

type TradeRow = {
  id: string;
  market_type: string;
  strategy_name: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  stop_loss_price: string | null;
  take_profit_price: string | null;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
};

type StrategyRow = {
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
};

type StreakRow = {
  final_outcome: string | null;
};

type FreqRow = {
  trading_days: string;
  total_resolved: string;
};

function withTimeout<T>(promise: Promise<T>, timeoutMs = 2500) {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Timed out while querying live bot data.")), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      }
    );
  });
}

function toNumber(value: string | number | null | undefined) {
  if (value == null) {
    return 0;
  }

  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function toProfitFactor(grossProfit: string | null, grossLoss: string | null) {
  const profit = toNumber(grossProfit);
  const loss = toNumber(grossLoss);
  if (loss <= 0) {
    return profit > 0 ? null : 0;
  }
  return profit / loss;
}

function mapOverview(row: OverviewRow | undefined | null): BotOverviewMetrics | null {
  if (!row) {
    return null;
  }

  return {
    resolvedTrades: toNumber(row.resolved_trades),
    wins: toNumber(row.wins),
    losses: toNumber(row.losses),
    takeProfits: toNumber(row.take_profits),
    heldToExpiryLosses: toNumber(row.held_to_expiry_losses),
    stopLosses: toNumber(row.stop_losses),
    openTrades: toNumber(row.open_trades),
    totalPnl: toNumber(row.total_pnl),
    avgPnlPerTrade: toNumber(row.avg_pnl_per_trade),
    profitFactor: toProfitFactor(row.gross_profit, row.gross_loss),
    lastTradeAt: row.last_trade_at,
  };
}

function mapWindow(row: OverviewRow | undefined | null): BotWindowMetrics | null {
  if (!row) {
    return null;
  }

  return {
    trades: toNumber(row.resolved_trades),
    wins: toNumber(row.wins),
    losses: toNumber(row.losses),
    takeProfits: toNumber(row.take_profits),
    heldToExpiryLosses: toNumber(row.held_to_expiry_losses),
    stopLosses: toNumber(row.stop_losses),
    openTrades: toNumber(row.open_trades),
    totalPnl: toNumber(row.total_pnl),
    avgPnlPerTrade: toNumber(row.avg_pnl_per_trade),
    profitFactor: toProfitFactor(row.gross_profit, row.gross_loss),
  };
}

function buildHourlySeries(rows: HourlyRow[]) {
  const rowMap = new Map(
    rows.map((row) => [new Date(row.hour_bucket).toISOString().slice(0, 13), row])
  );

  const points: BotActivityPoint[] = [];
  const now = new Date();
  now.setUTCMinutes(0, 0, 0);

  for (let offset = 23; offset >= 0; offset -= 1) {
    const bucket = new Date(now);
    bucket.setUTCHours(bucket.getUTCHours() - offset);
    const key = bucket.toISOString().slice(0, 13);
    const row = rowMap.get(key);

    points.push({
      hour: bucket.toLocaleTimeString("en-US", {
        hour: "numeric",
        hour12: false,
        timeZone: "UTC",
      }),
      trades: toNumber(row?.trades),
      wins: toNumber(row?.wins),
      pnl: toNumber(row?.pnl),
    });
  }

  return points;
}

function computeStreak(rows: StreakRow[]): BotStreakMetrics {
  if (rows.length === 0) return { type: "none", length: 0 };
  const first = rows[0].final_outcome;
  if (!first) return { type: "none", length: 0 };
  const isWin = ["win_resolution", "take_profit"].includes(first);
  let length = 0;
  for (const row of rows) {
    const outcome = row.final_outcome;
    if (!outcome) break;
    const rowIsWin = ["win_resolution", "take_profit"].includes(outcome);
    if (rowIsWin === isWin) length++;
    else break;
  }
  return { type: isWin ? "win" : "loss", length };
}

function deriveExitPrice(finalOutcome: string | null, stopLossPrice: string | null, takeProfitPrice: string | null) {
  if (finalOutcome === "win" || finalOutcome === "win_resolution") {
    return 1;
  }

  if (finalOutcome === "loss") {
    return 0;
  }

  if (finalOutcome === "stop_loss") {
    if (stopLossPrice == null) {
      return null;
    }
    const numeric = Number(stopLossPrice);
    return Number.isFinite(numeric) ? numeric : null;
  }

  if (finalOutcome === "take_profit") {
    if (takeProfitPrice == null) {
      return null;
    }
    const numeric = Number(takeProfitPrice);
    return Number.isFinite(numeric) ? numeric : null;
  }

  return null;
}

export async function getBotDashboardData(): Promise<BotDashboardData> {
  try {
    const [overallRows, last24Rows, previous24Rows, hourlyRows, tradeRows, strategyRows, drawdownRows, streakRows, freqRows] = await Promise.all([
      withTimeout(
        query<OverviewRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc > 0) AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc < 0) AS losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'take_profit') AS take_profits,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS held_to_expiry_losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS total_pnl,
            AVG(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN pnl_calc > 0 THEN pnl_calc ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN pnl_calc < 0 THEN pnl_calc ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM all_trades
        `)
      ),
      withTimeout(
        query<OverviewRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc > 0) AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc < 0) AS losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'take_profit') AS take_profits,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS held_to_expiry_losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS total_pnl,
            AVG(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN pnl_calc > 0 THEN pnl_calc ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN pnl_calc < 0 THEN pnl_calc ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM all_trades
          WHERE placed_at > NOW() - INTERVAL '24 hours'
        `)
      ),
      withTimeout(
        query<OverviewRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc > 0) AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc < 0) AS losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'take_profit') AS take_profits,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS held_to_expiry_losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS total_pnl,
            AVG(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN pnl_calc > 0 THEN pnl_calc ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN pnl_calc < 0 THEN pnl_calc ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM all_trades
          WHERE placed_at > NOW() - INTERVAL '48 hours'
            AND placed_at <= NOW() - INTERVAL '24 hours'
        `)
      ),
      withTimeout(
        query<HourlyRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            date_trunc('hour', placed_at) AS hour_bucket,
            COUNT(*) FILTER (WHERE status = 'filled') AS trades,
            COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss') AND pnl_calc > 0) AS wins,
            SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')) AS pnl
          FROM all_trades
          WHERE placed_at > NOW() - INTERVAL '24 hours'
          GROUP BY 1
          ORDER BY 1
        `)
      ),
      withTimeout(
        query<TradeRow>(`
          SELECT
            id,
            market_type,
            strategy_name,
            direction,
            entry_price,
            bet_size_usd,
            stop_loss_price,
            take_profit_price,
            status,
            final_outcome,
            COALESCE(pnl, ${PNL_SQL}) AS pnl,
            placed_at,
            resolved_at
          FROM bot_trades
          WHERE strategy_name NOT LIKE 'momentum%'
          ORDER BY placed_at DESC
          LIMIT 50
        `)
      ),
      withTimeout(
        query<StrategyRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            strategy_name,
            COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) AS trades,
            COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit')) AS wins,
            COUNT(*) FILTER (WHERE final_outcome IN ('loss','stop_loss')) AS losses,
            SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) AS pnl,
            AVG(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) AS avg_pnl
          FROM all_trades
          WHERE status = 'filled'
            AND strategy_name NOT LIKE 'momentum%'
          GROUP BY strategy_name
          ORDER BY SUM(pnl_calc) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) DESC NULLS LAST
        `)
      ).catch(() => [] as StrategyRow[]),
      withTimeout(
        query<DrawdownRow>(`
          WITH ${ALL_TRADES_CTE}, cumulative AS (
            SELECT
              placed_at,
              SUM(pnl_calc) OVER (ORDER BY placed_at) AS running_pnl
            FROM all_trades
            WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')
          ),
          with_peak AS (
            SELECT
              placed_at,
              running_pnl,
              MAX(running_pnl) OVER (ORDER BY placed_at) AS peak
            FROM cumulative
          ),
          last_row AS (
            SELECT running_pnl - peak AS current_drawdown
            FROM with_peak
            ORDER BY placed_at DESC
            LIMIT 1
          )
          SELECT
            MIN(running_pnl - peak) AS max_drawdown,
            (SELECT current_drawdown FROM last_row) AS current_drawdown
          FROM with_peak
        `)
      ).catch(() => [] as DrawdownRow[]),
      withTimeout(
        query<StreakRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT final_outcome
          FROM all_trades
          WHERE status = 'filled' AND final_outcome IN ('win_resolution','take_profit','loss','stop_loss')
          ORDER BY resolved_at DESC NULLS LAST, placed_at DESC
          LIMIT 50
        `)
      ).catch(() => [] as StreakRow[]),
      withTimeout(
        query<FreqRow>(`
          WITH ${ALL_TRADES_CTE}
          SELECT
            COUNT(DISTINCT DATE(placed_at)) AS trading_days,
            COUNT(*) FILTER (WHERE final_outcome IN ('win_resolution','take_profit','loss','stop_loss')) AS total_resolved
          FROM all_trades
          WHERE status = 'filled'
        `)
      ).catch(() => [] as FreqRow[]),
    ]);

    const freq = freqRows[0];
    const tradingDays = freq ? toNumber(freq.trading_days) : 0;
    const totalResolved = freq ? toNumber(freq.total_resolved) : 0;

    let maxDrawdown = 0;
    let currentDrawdown = 0;
    if (drawdownRows.length > 0 && drawdownRows[0].max_drawdown != null) {
      maxDrawdown = parseFloat(drawdownRows[0].max_drawdown);
      currentDrawdown = parseFloat(drawdownRows[0].current_drawdown ?? "0");
    }

    return {
      connected: true,
      error: null,
      overall: mapOverview(overallRows[0]),
      last24Hours: mapWindow(last24Rows[0]),
      previous24Hours: mapWindow(previous24Rows[0]),
      activity24Hours: buildHourlySeries(hourlyRows),
      recentTrades: tradeRows.map((row) => ({
        id: row.id,
        marketType: row.market_type,
        strategyName: row.strategy_name,
        side: row.direction,
        entryPrice: toNumber(row.entry_price),
        exitPrice: deriveExitPrice(row.final_outcome, row.stop_loss_price, row.take_profit_price),
        betSize: toNumber(row.bet_size_usd),
        pnl: row.pnl == null ? null : toNumber(row.pnl),
        placedAt: row.placed_at,
        resolvedAt: row.resolved_at,
        status: row.status,
        finalOutcome: row.final_outcome,
      })),
      strategyBreakdown: strategyRows.map((s) => {
        const trades = toNumber(s.trades);
        const wins = toNumber(s.wins);
        return {
          strategyName: s.strategy_name,
          trades,
          wins,
          losses: toNumber(s.losses),
          pnl: toNumber(s.pnl),
          avgPnl: toNumber(s.avg_pnl),
          winRate: trades > 0 ? (wins / trades) * 100 : 0,
        };
      }),
      drawdown: {
        maxDrawdown: isNaN(maxDrawdown) ? 0 : maxDrawdown,
        currentDrawdown: isNaN(currentDrawdown) ? 0 : currentDrawdown,
      },
      streak: computeStreak(streakRows),
      tradesPerDay: tradingDays > 0 ? parseFloat((totalResolved / tradingDays).toFixed(1)) : 0,
    };
  } catch (error) {
    console.error("Failed to load live bot dashboard data:", error);
    return {
      connected: false,
      error: "Live bot data is currently unavailable.",
      overall: null,
      last24Hours: null,
      previous24Hours: null,
      activity24Hours: [],
      recentTrades: [],
      strategyBreakdown: [],
      drawdown: { maxDrawdown: 0, currentDrawdown: 0 },
      streak: { type: "none", length: 0 },
      tradesPerDay: 0,
    };
  }
}
