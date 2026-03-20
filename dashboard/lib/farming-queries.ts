import { query } from "./db";

export interface FarmingRun {
  id: number;
  ran_at: string;
  markets_tested: number;
  total_combinations: number;
  date_range_start: string;
  date_range_end: string;
}

export interface FarmingResult {
  id: number;
  farming_run_id: number;
  market_type: string;
  trigger_point: number;
  exit_point: number;
  trigger_minutes: number;
  min_coin_delta: number;
  trades_taken: number;
  wins: number;
  losses: number;
  stop_losses: number;
  total_pnl: number;
  roi: number;
  win_rate: number;
  avg_entry_price: number;
  avg_coin_delta: number;
  avg_pnl_per_trade: number;
}

export interface FarmingData {
  run: FarmingRun | null;
  results: FarmingResult[];
}

export async function getFarmingData(): Promise<FarmingData> {
  const runs = await query<Record<string, unknown>>(
    "SELECT * FROM farming_runs ORDER BY ran_at DESC LIMIT 1"
  );

  if (runs.length === 0) {
    return { run: null, results: [] };
  }

  const run = runs[0];
  const runId = run.id as number;

  const rawResults = await query<Record<string, unknown>>(
    "SELECT * FROM farming_results WHERE farming_run_id = $1 ORDER BY total_pnl DESC",
    [runId]
  );

  const results: FarmingResult[] = rawResults.map((r) => ({
    id: Number(r.id),
    farming_run_id: Number(r.farming_run_id),
    market_type: String(r.market_type),
    trigger_point: parseFloat(String(r.trigger_point)),
    exit_point: parseFloat(String(r.exit_point)),
    trigger_minutes: Number(r.trigger_minutes),
    min_coin_delta: parseFloat(String(r.min_coin_delta)),
    trades_taken: Number(r.trades_taken),
    wins: Number(r.wins),
    losses: Number(r.losses),
    stop_losses: Number(r.stop_losses),
    total_pnl: parseFloat(String(r.total_pnl)),
    roi: parseFloat(String(r.roi)),
    win_rate: parseFloat(String(r.win_rate)),
    avg_entry_price: parseFloat(String(r.avg_entry_price)),
    avg_coin_delta: parseFloat(String(r.avg_coin_delta)),
    avg_pnl_per_trade: parseFloat(String(r.avg_pnl_per_trade)),
  }));

  const parsedRun: FarmingRun = {
    id: Number(run.id),
    ran_at: String(run.ran_at),
    markets_tested: Number(run.markets_tested),
    total_combinations: Number(run.total_combinations),
    date_range_start: String(run.date_range_start),
    date_range_end: String(run.date_range_end),
  };

  return { run: parsedRun, results };
}
