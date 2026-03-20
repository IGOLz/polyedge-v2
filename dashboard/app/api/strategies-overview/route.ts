export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getStrategiesOverview } from "@/lib/strategies-overview-queries";

export async function GET() {
  try {
    const data = await getStrategiesOverview();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch strategies overview:", error);
    return NextResponse.json({ strategies: [] });
  }
}
