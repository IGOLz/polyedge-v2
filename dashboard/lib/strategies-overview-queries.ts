import { query } from "./db";

interface StrategyResult {
  strategy: string;
  name: string;
  total_pnl: number | null;
  roi: number | null;
  win_rate: number | null;
  trades_taken: number | null;
  param1: number | null;
  param2: number | null;
  href: string;
}

export async function getStrategiesOverview(): Promise<{ strategies: StrategyResult[] }> {
  const strategies: StrategyResult[] = [
    { strategy: "S1", name: "Farming", total_pnl: null, roi: null, win_rate: null, trades_taken: null, param1: null, param2: null, href: "/strategy" },
    { strategy: "S2", name: "Calibration", total_pnl: null, roi: null, win_rate: null, trades_taken: null, param1: null, param2: null, href: "/strategy2" },
    { strategy: "S3", name: "Momentum", total_pnl: null, roi: null, win_rate: null, trades_taken: null, param1: null, param2: null, href: "/strategy3" },
    { strategy: "S4", name: "Streak Reversal", total_pnl: null, roi: null, win_rate: null, trades_taken: null, param1: null, param2: null, href: "/strategy4" },
  ];

  // Strategy 1: Farming
  try {
    const rows = await query<{
      total_pnl: string;
      roi: string;
      win_rate: string;
      trades_taken: number;
      param1: number;
      param2: number;
    }>(
      `SELECT total_pnl, roi, win_rate, trades_taken,
              trigger_point as param1, exit_point as param2
       FROM farming_results
       WHERE farming_run_id = (SELECT MAX(id) FROM farming_runs)
         AND trades_taken >= 10
       ORDER BY total_pnl DESC LIMIT 1`
    );
    if (rows.length > 0) {
      strategies[0].total_pnl = parseFloat(String(rows[0].total_pnl));
      strategies[0].roi = parseFloat(String(rows[0].roi));
      strategies[0].win_rate = parseFloat(String(rows[0].win_rate));
      strategies[0].trades_taken = rows[0].trades_taken;
      strategies[0].param1 = rows[0].param1;
      strategies[0].param2 = rows[0].param2;
    }
  } catch { /* table may not exist */ }

  // Strategy 2: Calibration
  try {
    const rows = await query<{
      total_pnl: string;
      roi: string;
      win_rate: string;
      trades_taken: number;
      param1: number;
      param2: number;
    }>(
      `SELECT total_pnl, roi, win_rate, trades_taken,
              entry_price_low as param1, entry_price_high as param2
       FROM calibration_strategy_results
       WHERE strategy_run_id = (SELECT MAX(id) FROM calibration_strategy_runs)
         AND trades_taken >= 10
       ORDER BY total_pnl DESC LIMIT 1`
    );
    if (rows.length > 0) {
      strategies[1].total_pnl = parseFloat(String(rows[0].total_pnl));
      strategies[1].roi = parseFloat(String(rows[0].roi));
      strategies[1].win_rate = parseFloat(String(rows[0].win_rate));
      strategies[1].trades_taken = rows[0].trades_taken;
      strategies[1].param1 = rows[0].param1;
      strategies[1].param2 = rows[0].param2;
    }
  } catch { /* table may not exist */ }

  // Strategy 3: Momentum
  try {
    const rows = await query<{
      total_pnl: string;
      roi: string;
      win_rate: string;
      trades_taken: number;
      param1: number;
    }>(
      `SELECT total_pnl, roi, win_rate, trades_taken,
              min_momentum as param1
       FROM momentum_strategy_results
       WHERE strategy_run_id = (SELECT MAX(id) FROM momentum_strategy_runs)
         AND trades_taken >= 10
       ORDER BY total_pnl DESC LIMIT 1`
    );
    if (rows.length > 0) {
      strategies[2].total_pnl = parseFloat(String(rows[0].total_pnl));
      strategies[2].roi = parseFloat(String(rows[0].roi));
      strategies[2].win_rate = parseFloat(String(rows[0].win_rate));
      strategies[2].trades_taken = rows[0].trades_taken;
      strategies[2].param1 = rows[0].param1;
    }
  } catch { /* table may not exist */ }

  // Strategy 4: Streak
  try {
    const rows = await query<{
      total_pnl: string;
      roi: string;
      win_rate: string;
      trades_taken: number;
      param1: number;
    }>(
      `SELECT total_pnl, roi, win_rate, trades_taken,
              streak_length as param1
       FROM streak_strategy_results
       WHERE strategy_run_id = (SELECT MAX(id) FROM streak_strategy_runs)
         AND trades_taken >= 10
       ORDER BY total_pnl DESC LIMIT 1`
    );
    if (rows.length > 0) {
      strategies[3].total_pnl = parseFloat(String(rows[0].total_pnl));
      strategies[3].roi = parseFloat(String(rows[0].roi));
      strategies[3].win_rate = parseFloat(String(rows[0].win_rate));
      strategies[3].trades_taken = rows[0].trades_taken;
      strategies[3].param1 = rows[0].param1;
    }
  } catch { /* table may not exist */ }

  return { strategies };
}
