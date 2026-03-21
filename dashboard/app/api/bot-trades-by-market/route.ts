export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

type MarketTrade = {
  [key: string]: unknown;
  id: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
  confidence_multiplier: string | null;
  stop_loss_price: string | null;
  stop_loss_triggered: boolean | null;
  strategy_name: string;
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const marketId = searchParams.get("market_id");

  if (!marketId) {
    return NextResponse.json([], { status: 400 });
  }

  try {
    const trades = await query<MarketTrade>(
      `SELECT
        id, direction, entry_price, bet_size_usd, status,
        final_outcome, ${PNL_SQL} as pnl, placed_at, resolved_at,
        confidence_multiplier, stop_loss_price, stop_loss_triggered,
        strategy_name
      FROM bot_trades
      WHERE market_id = $1 AND status = 'filled'
      ORDER BY placed_at ASC`,
      [marketId]
    );

    return NextResponse.json(trades);
  } catch (error) {
    console.error("Failed to fetch trades for market:", error);
    return NextResponse.json([], { status: 500 });
  }
}
