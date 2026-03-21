export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { REVALIDATE_SECONDS } from "@/lib/constants";

export const revalidate = REVALIDATE_SECONDS;

export async function GET() {
  try {
    const rows = await query<{
      market_id: string;
      market_type: string;
      started_at: string;
      ended_at: string;
      final_outcome: string | null;
      resolved: boolean;
      tick_count: string;
    }>(`
      SELECT
        mo.market_id,
        mo.market_type,
        mo.started_at,
        mo.ended_at,
        mo.final_outcome,
        mo.resolved,
        COALESCE(tc.tick_count, 0) as tick_count
      FROM market_outcomes mo
      LEFT JOIN (
        SELECT market_id, COUNT(*) as tick_count
        FROM market_ticks
        GROUP BY market_id
      ) tc ON mo.market_id = tc.market_id
      ORDER BY mo.started_at DESC
    `);

    return NextResponse.json(rows);
  } catch (error) {
    console.error("Failed to fetch markets:", error);
    return NextResponse.json({ error: "Failed to fetch markets" }, { status: 500 });
  }
}
