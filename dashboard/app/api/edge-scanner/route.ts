export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getEdgeScannerData } from "@/lib/queries";

export async function GET() {
  try {
    const data = await getEdgeScannerData();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch edge scanner data:", error);
    return NextResponse.json({ error: "Failed to fetch edge scanner data" }, { status: 500 });
  }
}
