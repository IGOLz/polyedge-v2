export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getFarmingData } from "@/lib/farming-queries";

export async function GET() {
  try {
    const data = await getFarmingData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch farming data:", error);
    return NextResponse.json({ run: null, results: [] });
  }
}
