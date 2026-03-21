export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getTickRates } from "@/lib/queries";
import { REVALIDATE_SECONDS } from "@/lib/constants";

export const revalidate = REVALIDATE_SECONDS;

export async function GET() {
  try {
    const rates = await getTickRates();
    return NextResponse.json(rates);
  } catch (error) {
    console.error("Failed to fetch tick rates:", error);
    return NextResponse.json(
      { error: "Failed to fetch tick rates" },
      { status: 500 }
    );
  }
}
