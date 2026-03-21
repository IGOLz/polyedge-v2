export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getMomentumStrategyData } from "@/lib/momentum-queries";

export async function GET() {
  try {
    const data = await getMomentumStrategyData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch momentum strategy data:", error);
    return NextResponse.json({ run: null, results: [] });
  }
}
