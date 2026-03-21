import { query } from "./db";

export interface CalibrationRun {
  id: number;
  ran_at: string;
  markets_tested: number;
  total_combinations: number;
  date_range_start: string;
  date_range_end: string;
}

export interface CalibrationResult {
  id: number;
  strategy_run_id: number;
  market_type: string;
  max_entry_seconds: number;
  entry_price_low: number;
  entry_price_high: number;
  min_deviation: number;
  trades_taken: number;
  wins: number;
  losses: number;
  up_trades: number;
  down_trades: number;
  total_pnl: number;
  roi: number;
  win_rate: number;
  avg_entry_price: number;
  avg_pnl_per_trade: number;
}

export interface CalibrationData {
  run: CalibrationRun | null;
  results: CalibrationResult[];
}

export async function getCalibrationStrategyData(): Promise<CalibrationData> {
  const runs = await query<Record<string, unknown>>(
    "SELECT * FROM calibration_strategy_runs ORDER BY ran_at DESC LIMIT 1"
  );

  if (runs.length === 0) {
    return { run: null, results: [] };
  }

  const run = runs[0];
  const runId = run.id as number;

  const rawResults = await query<Record<string, unknown>>(
    "SELECT * FROM calibration_strategy_results WHERE strategy_run_id = $1 ORDER BY total_pnl DESC",
    [runId]
  );

  const results: CalibrationResult[] = rawResults.map((r) => ({
    id: Number(r.id),
    strategy_run_id: Number(r.strategy_run_id),
    market_type: String(r.market_type),
    max_entry_seconds: Number(r.max_entry_seconds),
    entry_price_low: parseFloat(String(r.entry_price_low)),
    entry_price_high: parseFloat(String(r.entry_price_high)),
    min_deviation: parseFloat(String(r.min_deviation)),
    trades_taken: Number(r.trades_taken),
    wins: Number(r.wins),
    losses: Number(r.losses),
    up_trades: Number(r.up_trades),
    down_trades: Number(r.down_trades),
    total_pnl: parseFloat(String(r.total_pnl)),
    roi: parseFloat(String(r.roi)),
    win_rate: parseFloat(String(r.win_rate)),
    avg_entry_price: parseFloat(String(r.avg_entry_price)),
    avg_pnl_per_trade: parseFloat(String(r.avg_pnl_per_trade)),
  }));

  const parsedRun: CalibrationRun = {
    id: Number(run.id),
    ran_at: String(run.ran_at),
    markets_tested: Number(run.markets_tested),
    total_combinations: Number(run.total_combinations),
    date_range_start: String(run.date_range_start),
    date_range_end: String(run.date_range_end),
  };

  return { run: parsedRun, results };
}
