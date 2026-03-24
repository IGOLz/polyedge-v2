import { query } from "@/lib/db";

export interface BotColdmathStats {
  totalPositions: number;
  closedPositions: number;
  openPositions: number;
  totalEntryCost: number;
  totalMergedUsdc: number;
  totalRedeemedUsdc: number;
  totalUnwindUsdc: number;
  realizedPnl: number;
  avgPnlPerPosition: number;
  firstTradeAt: string | null;
  lastTradeAt: string | null;
}

export interface TrackedUserStats {
  totalActivities: number;
  totalTrades: number;
  totalBuys: number;
  totalSells: number;
  totalMerges: number;
  totalSplits: number;
  totalRedeems: number;
  totalSpent: number;
  totalSold: number;
  totalMergedUsdc: number;
  totalRedeemedUsdc: number;
  netPnl: number;
  avgTradeSize: number;
  distinctMarkets: number;
  profileName: string;
  firstActivityAt: string | null;
  lastActivityAt: string | null;
  trackingSince: string | null;
}

export interface ColdmathComparisonData {
  bot: BotColdmathStats | null;
  trackedUser: TrackedUserStats | null;
}

type BotRow = {
  total_positions: string;
  closed_positions: string;
  open_positions: string;
  total_entry_cost: string | null;
  total_merged_usdc: string | null;
  total_redeemed_usdc: string | null;
  total_unwind_usdc: string | null;
  realized_pnl: string | null;
  avg_pnl: string | null;
  first_trade_at: string | null;
  last_trade_at: string | null;
};

type TrackedRow = {
  total_activities: string;
  total_trades: string;
  total_buys: string;
  total_sells: string;
  total_merges: string;
  total_splits: string;
  total_redeems: string;
  total_spent: string | null;
  total_sold: string | null;
  total_merged_usdc: string | null;
  total_redeemed_usdc: string | null;
  net_pnl: string | null;
  avg_trade_size: string | null;
  distinct_markets: string;
  profile_name: string | null;
  first_activity_at: string | null;
  last_activity_at: string | null;
  tracking_since: string | null;
};

function toNum(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export async function getColdmathComparisonData(): Promise<ColdmathComparisonData> {
  let bot: BotColdmathStats | null = null;
  let trackedUser: TrackedUserStats | null = null;

  try {
    const botRows = await query<BotRow>(`
      SELECT
        COUNT(*) AS total_positions,
        COUNT(*) FILTER (WHERE closed_at IS NOT NULL) AS closed_positions,
        COUNT(*) FILTER (WHERE closed_at IS NULL) AS open_positions,
        SUM(total_entry_cost) AS total_entry_cost,
        SUM(merged_collateral_usdc) AS total_merged_usdc,
        SUM(redeemed_collateral_usdc) AS total_redeemed_usdc,
        SUM(unwind_collateral_usdc) AS total_unwind_usdc,
        SUM(
          CASE WHEN closed_at IS NOT NULL
            THEN merged_collateral_usdc + redeemed_collateral_usdc + unwind_collateral_usdc - total_entry_cost
            ELSE 0
          END
        ) AS realized_pnl,
        AVG(
          CASE WHEN closed_at IS NOT NULL
            THEN merged_collateral_usdc + redeemed_collateral_usdc + unwind_collateral_usdc - total_entry_cost
            ELSE NULL
          END
        ) AS avg_pnl,
        MIN(opened_at) AS first_trade_at,
        MAX(opened_at) AS last_trade_at
      FROM weather_merge_positions
    `);
    const r = botRows[0];
    if (r && toNum(r.total_positions) > 0) {
      bot = {
        totalPositions: toNum(r.total_positions),
        closedPositions: toNum(r.closed_positions),
        openPositions: toNum(r.open_positions),
        totalEntryCost: toNum(r.total_entry_cost),
        totalMergedUsdc: toNum(r.total_merged_usdc),
        totalRedeemedUsdc: toNum(r.total_redeemed_usdc),
        totalUnwindUsdc: toNum(r.total_unwind_usdc),
        realizedPnl: toNum(r.realized_pnl),
        avgPnlPerPosition: toNum(r.avg_pnl),
        firstTradeAt: r.first_trade_at,
        lastTradeAt: r.last_trade_at,
      };
    }
  } catch (e) {
    console.error("[wallet-tracker] bot query failed:", e);
  }

  try {
    const trackedRows = await query<TrackedRow>(`
      SELECT
        COUNT(*) AS total_activities,
        COUNT(*) FILTER (WHERE event_type = 'TRADE') AS total_trades,
        COUNT(*) FILTER (WHERE event_type = 'TRADE' AND side = 'BUY') AS total_buys,
        COUNT(*) FILTER (WHERE event_type = 'TRADE' AND side = 'SELL') AS total_sells,
        COUNT(*) FILTER (WHERE event_type = 'MERGE') AS total_merges,
        COUNT(*) FILTER (WHERE event_type = 'SPLIT') AS total_splits,
        COUNT(*) FILTER (WHERE event_type = 'REDEEM') AS total_redeems,
        COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'TRADE' AND side = 'BUY'), 0) AS total_spent,
        COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'TRADE' AND side = 'SELL'), 0) AS total_sold,
        COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'MERGE'), 0) AS total_merged_usdc,
        COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'REDEEM'), 0) AS total_redeemed_usdc,
        COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'TRADE' AND side = 'SELL'), 0)
          + COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'MERGE'), 0)
          + COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'REDEEM'), 0)
          - COALESCE(SUM(usdc_size) FILTER (WHERE event_type = 'TRADE' AND side = 'BUY'), 0)
        AS net_pnl,
        AVG(usdc_size) FILTER (WHERE usdc_size IS NOT NULL AND event_type = 'TRADE') AS avg_trade_size,
        COUNT(DISTINCT condition_id) AS distinct_markets,
        MAX(profile_name) AS profile_name,
        TO_TIMESTAMP(MIN(timestamp)) AS first_activity_at,
        TO_TIMESTAMP(MAX(timestamp)) AS last_activity_at,
        MIN(fetched_at) AS tracking_since
      FROM wallet_tracker_activity
    `);
    const t = trackedRows[0];
    if (t && toNum(t.total_activities) > 0) {
      trackedUser = {
        totalActivities: toNum(t.total_activities),
        totalTrades: toNum(t.total_trades),
        totalBuys: toNum(t.total_buys),
        totalSells: toNum(t.total_sells),
        totalMerges: toNum(t.total_merges),
        totalSplits: toNum(t.total_splits),
        totalRedeems: toNum(t.total_redeems),
        totalSpent: toNum(t.total_spent),
        totalSold: toNum(t.total_sold),
        totalMergedUsdc: toNum(t.total_merged_usdc),
        totalRedeemedUsdc: toNum(t.total_redeemed_usdc),
        netPnl: toNum(t.net_pnl),
        avgTradeSize: toNum(t.avg_trade_size),
        distinctMarkets: toNum(t.distinct_markets),
        profileName: t.profile_name ?? "ColdMath",
        firstActivityAt: t.first_activity_at,
        lastActivityAt: t.last_activity_at,
        trackingSince: t.tracking_since,
      };
    }
  } catch (e) {
    console.error("[wallet-tracker] tracked user query failed:", e);
  }

  return { bot, trackedUser };
}
