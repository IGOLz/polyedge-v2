import { query } from "./db";

export interface StreakRun {
  id: number;
  ran_at: string;
  markets_tested: number;
  total_combinations: number;
  date_range_start: string;
  date_range_end: string;
}

export interface StreakResult {
  id: number;
  strategy_run_id: number;
  streak_length: number;
  streak_direction: string;
  market_type: string;
  total_markets: number;
  trades_taken: number;
  entry_rate: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  roi: number;
  avg_pnl_per_trade: number;
  avg_entry_price: number;
  up_trades: number;
  down_trades: number;
}

export interface StreakData {
  run: StreakRun | null;
  results: StreakResult[];
}

export async function getStreakStrategyData(): Promise<StreakData> {
  const runs = await query<Record<string, unknown>>(
    "SELECT * FROM streak_strategy_runs ORDER BY ran_at DESC LIMIT 1"
  );

  if (runs.length === 0) {
    return { run: null, results: [] };
  }

  const run = runs[0];
  const runId = run.id as number;

  const rawResults = await query<Record<string, unknown>>(
    "SELECT * FROM streak_strategy_results WHERE strategy_run_id = $1 ORDER BY total_pnl DESC",
    [runId]
  );

  const results: StreakResult[] = rawResults.map((r) => ({
    id: Number(r.id),
    strategy_run_id: Number(r.strategy_run_id),
    streak_length: Number(r.streak_length),
    streak_direction: String(r.streak_direction),
    market_type: String(r.market_type),
    total_markets: Number(r.total_markets),
    trades_taken: Number(r.trades_taken),
    entry_rate: parseFloat(String(r.entry_rate)),
    wins: Number(r.wins),
    losses: Number(r.losses),
    win_rate: parseFloat(String(r.win_rate)),
    total_pnl: parseFloat(String(r.total_pnl)),
    roi: parseFloat(String(r.roi)),
    avg_pnl_per_trade: parseFloat(String(r.avg_pnl_per_trade)),
    avg_entry_price: parseFloat(String(r.avg_entry_price)),
    up_trades: Number(r.up_trades),
    down_trades: Number(r.down_trades),
  }));

  const parsedRun: StreakRun = {
    id: Number(run.id),
    ran_at: String(run.ran_at),
    markets_tested: Number(run.markets_tested),
    total_combinations: Number(run.total_combinations),
    date_range_start: String(run.date_range_start),
    date_range_end: String(run.date_range_end),
  };

  return { run: parsedRun, results };
}
