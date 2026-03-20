import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rows = await query<{ key: string; value: string; updated_at: string }>(
    "SELECT key, value, updated_at FROM bot_config ORDER BY key"
  );

  return NextResponse.json(rows);
}

export async function POST(request: NextRequest) {
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { key, value } = await request.json();

  if (!key || value === undefined || value === null) {
    return NextResponse.json(
      { error: "Missing key or value" },
      { status: 400 }
    );
  }

  await query(
    `INSERT INTO bot_config (key, value, updated_at)
     VALUES ($1, $2, NOW())
     ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()`,
    [key, String(value)]
  );

  return NextResponse.json({ success: true });
}
