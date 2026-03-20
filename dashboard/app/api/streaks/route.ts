export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getStreakData } from "@/lib/queries";

export async function GET() {
  try {
    const data = await getStreakData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch streak data:", error);
    return NextResponse.json([]);
  }
}
