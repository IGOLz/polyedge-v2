export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";

type BotTrade = {
  id: string;
  market_type: string;
  strategy_name: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
  signal_data: Record<string, unknown> | null;
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
    const trades = await query<BotTrade>(
      `SELECT id, market_type, strategy_name, direction, entry_price, bet_size_usd, status, final_outcome, ${PNL_SQL} as pnl, placed_at, resolved_at, signal_data
       FROM bot_trades
       ORDER BY placed_at DESC`
    );

    const SIGNAL_KEYS = [
      // Shared
      "entry_price", "shares", "bet_cost", "bet_size", "stop_loss_price",
      "balance_at_signal", "seconds_elapsed", "seconds_remaining",
      // M4 volatility
      "up_price", "down_price", "spread", "volatility_avg", "volatility_up",
      "volatility_down", "eval_second",
      // M3 spike reversion
      "spike_direction", "spike_price", "spike_tick", "reversion_target",
      "reversion_tick", "reversion_ticks_elapsed",
      // Legacy momentum
      "price_a_seconds", "price_b_seconds", "price_a", "price_b", "price_open",
      "momentum_value",
    ] as const;

    const headers = [
      "ID", "Market Type", "Strategy", "Direction", "Entry Price",
      "Bet Size (USD)", "Status", "Outcome", "PnL", "Placed At", "Resolved At",
      ...SIGNAL_KEYS.map((k) => `signal_${k}`),
    ];

    const rows = trades.map((t) => {
      const sd = t.signal_data ?? {};
      return [
        t.id, t.market_type, t.strategy_name, t.direction, t.entry_price,
        t.bet_size_usd, t.status, t.final_outcome, t.pnl, t.placed_at, t.resolved_at,
        ...SIGNAL_KEYS.map((k) => sd[k] != null ? String(sd[k]) : null),
      ].map(escapeCsv).join(",");
    });

    const csv = [headers.join(","), ...rows].join("\n");
    const date = new Date().toISOString().slice(0, 10);

    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": `attachment; filename="bot-trades-${date}.csv"`,
      },
    });
  } catch (error) {
    console.error("Failed to export trades:", error);
    return NextResponse.json({ error: "Failed to export trades" }, { status: 500 });
  }
}
