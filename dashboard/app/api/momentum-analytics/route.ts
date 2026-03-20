export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { query } from "@/lib/db";

type MomentumTrade = {
  [key: string]: unknown;
  id: string;
  market_id: string | null;
  market_type: string;
  strategy_name: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
  stop_loss_price: string | null;
  stop_loss_triggered: boolean | null;
  notes: string | null;
};

type ConfigRow = {
  [key: string]: unknown;
  key: string;
  value: string;
};

const RANGE_MAP: Record<string, string> = {
  "24h": "NOW() - INTERVAL '24 hours'",
  "7d": "NOW() - INTERVAL '7 days'",
  "30d": "NOW() - INTERVAL '30 days'",
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const range = searchParams.get("range") || "7d";

  try {
    const timeFilter = RANGE_MAP[range];
    const timeClause = timeFilter ? `AND placed_at >= ${timeFilter}` : "";

    const [trades, tierConfig] = await Promise.all([
      query<MomentumTrade>(
        `SELECT
          id, market_id, market_type, strategy_name, direction,
          entry_price, bet_size_usd, status, final_outcome, pnl,
          placed_at, resolved_at, stop_loss_price, stop_loss_triggered,
          notes
        FROM bot_trades
        WHERE strategy_name IN ('momentum_broad', 'momentum_filtered', 'momentum_aggressive') AND status = 'filled'
        ${timeClause}
        ORDER BY placed_at DESC`,
      ),
      query<ConfigRow>(
        `SELECT key, value FROM bot_config
        WHERE key IN (
          'strategy_momentum_broad_enabled',
          'strategy_momentum_filtered_enabled',
          'strategy_momentum_aggressive_enabled'
        )`,
      ),
    ]);

    const tierStatus: Record<string, boolean> = {
      broad: false,
      filtered: false,
      aggressive: false,
    };
    tierConfig.forEach((row) => {
      if (row.key === "strategy_momentum_broad_enabled") tierStatus.broad = row.value === "true";
      if (row.key === "strategy_momentum_filtered_enabled") tierStatus.filtered = row.value === "true";
      if (row.key === "strategy_momentum_aggressive_enabled") tierStatus.aggressive = row.value === "true";
    });

    return NextResponse.json({ trades, tierStatus });
  } catch (error) {
    console.error("Failed to fetch momentum analytics:", error);
    return NextResponse.json({ trades: [], tierStatus: { broad: false, filtered: false, aggressive: false } }, { status: 500 });
  }
}
