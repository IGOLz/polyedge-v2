import "server-only";

import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

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
  pnl: number | null;
  placedAt: string;
  resolvedAt: string | null;
  status: string;
  finalOutcome: string | null;
}

export interface BotDashboardData {
  connected: boolean;
  error: string | null;
  overall: BotOverviewMetrics | null;
  last24Hours: BotWindowMetrics | null;
  previous24Hours: BotWindowMetrics | null;
  activity24Hours: BotActivityPoint[];
  recentTrades: RecentTradeRow[];
}

type OverviewRow = {
  resolved_trades: string;
  wins: string;
  losses: string;
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
  stop_loss_price: string | null;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
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
    takeProfits: toNumber(row.wins),
    heldToExpiryLosses: toNumber(row.losses),
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
    takeProfits: toNumber(row.wins),
    heldToExpiryLosses: toNumber(row.losses),
    stopLosses: toNumber(row.stop_losses),
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

function deriveExitPrice(finalOutcome: string | null, stopLossPrice: string | null) {
  if (finalOutcome === "win") {
    return 1;
  }

  if (finalOutcome === "loss") {
    return 0;
  }

  if (finalOutcome === "stop_loss") {
    const numeric = Number(stopLossPrice);
    return Number.isFinite(numeric) ? numeric : null;
  }

  return null;
}

export async function getBotDashboardData(): Promise<BotDashboardData> {
  try {
    const [overallRows, last24Rows, previous24Rows, hourlyRows, tradeRows] = await Promise.all([
      withTimeout(
        query<OverviewRow>(`
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NOT NULL) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'win') AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS total_pnl,
            AVG(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN (${PNL_SQL}) > 0 THEN (${PNL_SQL}) ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN (${PNL_SQL}) < 0 THEN (${PNL_SQL}) ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM bot_trades
        `)
      ),
      withTimeout(
        query<OverviewRow>(`
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NOT NULL) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'win') AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS total_pnl,
            AVG(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN (${PNL_SQL}) > 0 THEN (${PNL_SQL}) ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN (${PNL_SQL}) < 0 THEN (${PNL_SQL}) ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM bot_trades
          WHERE placed_at > NOW() - INTERVAL '24 hours'
        `)
      ),
      withTimeout(
        query<OverviewRow>(`
          SELECT
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NOT NULL) AS resolved_trades,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'win') AS wins,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome = 'loss') AS losses,
            COUNT(*) FILTER (WHERE final_outcome = 'stop_loss') AS stop_losses,
            COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
            SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS total_pnl,
            AVG(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS avg_pnl_per_trade,
            SUM(CASE WHEN (${PNL_SQL}) > 0 THEN (${PNL_SQL}) ELSE 0 END) AS gross_profit,
            ABS(SUM(CASE WHEN (${PNL_SQL}) < 0 THEN (${PNL_SQL}) ELSE 0 END)) AS gross_loss,
            MAX(placed_at) AS last_trade_at
          FROM bot_trades
          WHERE placed_at > NOW() - INTERVAL '48 hours'
            AND placed_at <= NOW() - INTERVAL '24 hours'
        `)
      ),
      withTimeout(
        query<HourlyRow>(`
          SELECT
            date_trunc('hour', placed_at) AS hour_bucket,
            COUNT(*) FILTER (WHERE status = 'filled') AS trades,
            COUNT(*) FILTER (WHERE final_outcome = 'win') AS wins,
            SUM(${PNL_SQL}) FILTER (WHERE final_outcome IN ('win', 'loss', 'stop_loss')) AS pnl
          FROM bot_trades
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
            stop_loss_price,
            status,
            final_outcome,
            COALESCE(pnl, ${PNL_SQL}) AS pnl,
            placed_at,
            resolved_at
          FROM bot_trades
          ORDER BY placed_at DESC
          LIMIT 18
        `)
      ),
    ]);

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
        exitPrice: deriveExitPrice(row.final_outcome, row.stop_loss_price),
        pnl: row.pnl == null ? null : toNumber(row.pnl),
        placedAt: row.placed_at,
        resolvedAt: row.resolved_at,
        status: row.status,
        finalOutcome: row.final_outcome,
      })),
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
    };
  }
}
