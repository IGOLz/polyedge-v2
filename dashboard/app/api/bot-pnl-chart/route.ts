export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

type PnlRow = {
  placed_at: string;
  pnl: string;
};

export async function GET() {
  try {
    const rows = await query<PnlRow>(`
      SELECT placed_at, ${PNL_SQL} as pnl
      FROM bot_trades
      WHERE final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')
      ORDER BY placed_at ASC
    `);
    return NextResponse.json({ trades: rows });
  } catch (error) {
    console.error("Failed to fetch PnL chart data:", error);
    return NextResponse.json({ trades: [] });
  }
}
