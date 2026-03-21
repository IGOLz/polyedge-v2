export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getCalibrationStrategyData } from "@/lib/calibration-queries";

export async function GET() {
  try {
    const data = await getCalibrationStrategyData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch calibration strategy data:", error);
    return NextResponse.json({ run: null, results: [] });
  }
}
