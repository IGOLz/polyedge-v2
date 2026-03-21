export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getStrategySummaries } from "@/lib/strategy-artifacts";

export async function GET() {
  try {
    const strategies = await getStrategySummaries();
    return NextResponse.json({ strategies });
  } catch (error) {
    console.error("Failed to fetch strategies overview:", error);
    return NextResponse.json({ strategies: [] });
  }
}
