export const dynamic = 'force-dynamic';

import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";
import { REVALIDATE_SECONDS } from "@/lib/constants";

export const revalidate = REVALIDATE_SECONDS;

export async function GET(request: NextRequest) {
  const marketId = request.nextUrl.searchParams.get("market_id");

  if (!marketId) {
    return NextResponse.json({ error: "market_id is required" }, { status: 400 });
  }

  try {
    const rows = await query<{
      seconds: string;
      up_price: string;
    }>(`
      SELECT
        EXTRACT(EPOCH FROM (mt.time - mo.started_at)) as seconds,
        mt.up_price
      FROM market_ticks mt
      JOIN market_outcomes mo ON mt.market_id = mo.market_id
      WHERE mt.market_id = $1
      ORDER BY mt.time ASC
    `, [marketId]);

    return NextResponse.json(
      rows.map((r) => ({
        seconds: Math.round(parseFloat(r.seconds)),
        up_price: parseFloat(r.up_price),
      }))
    );
  } catch (error) {
    console.error("Failed to fetch market ticks:", error);
    return NextResponse.json({ error: "Failed to fetch ticks" }, { status: 500 });
  }
}
