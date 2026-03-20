export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import {
  getOverviewStats,
  getMarketsByType,
  getRecentActivity,
  getTickRates,
} from "@/lib/queries";
import { REVALIDATE_SECONDS } from "@/lib/constants";

export const revalidate = REVALIDATE_SECONDS;

export async function GET() {
  try {
    const [overview, marketsByType, recentActivity, tickRates] =
      await Promise.all([
        getOverviewStats(),
        getMarketsByType(),
        getRecentActivity(),
        getTickRates(),
      ]);

    const data = {
      exportedAt: new Date().toISOString(),
      overview,
      marketsByType,
      recentActivity,
      tickRates,
    };

    return new NextResponse(JSON.stringify(data, null, 2), {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="polyedge-export-${new Date().toISOString().slice(0, 10)}.json"`,
      },
    });
  } catch (error) {
    console.error("Failed to export data:", error);
    return NextResponse.json(
      { error: "Failed to export data" },
      { status: 500 }
    );
  }
}
