export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { query } from "@/lib/db";

type BotLog = {
  id: string;
  log_type: string;
  message: string;
  logged_at: string;
};

function escapeCsv(val: string | null | undefined): string {
  if (val == null) return "";
  const s = String(val);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export async function GET() {
  try {
    const logs = await query<BotLog>(
      `SELECT id, log_type, message, logged_at
       FROM bot_logs
       ORDER BY logged_at DESC`
    );

    const headers = ["ID", "Type", "Message", "Logged At"];

    const rows = logs.map((l) =>
      [l.id, l.log_type, l.message, l.logged_at].map(escapeCsv).join(",")
    );

    const csv = [headers.join(","), ...rows].join("\n");
    const date = new Date().toISOString().slice(0, 10);

    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": `attachment; filename="bot-activity-${date}.csv"`,
      },
    });
  } catch (error) {
    console.error("Failed to export activity:", error);
    return NextResponse.json({ error: "Failed to export activity" }, { status: 500 });
  }
}
