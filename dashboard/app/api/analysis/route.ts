export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getAnalysisData } from "@/lib/queries";

export async function GET() {
  try {
    const data = await getAnalysisData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch analysis data:", error);
    return NextResponse.json(
      { run: null, calibration: [], trajectory: [], timeofday: [], sequential: [], heatmap: [] }
    );
  }
}
