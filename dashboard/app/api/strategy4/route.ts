export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getStreakStrategyData } from "@/lib/streak-queries";

export async function GET() {
  try {
    const data = await getStreakStrategyData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch streak strategy data:", error);
    return NextResponse.json({ run: null, results: [] });
  }
}
