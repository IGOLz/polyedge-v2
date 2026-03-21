import { query } from "./db";

export interface MomentumRun {
  id: number;
  ran_at: string;
  markets_tested: number;
  total_combinations: number;
  date_range_start: string;
  date_range_end: string;
}

export interface MomentumResult {
  id: number;
  strategy_run_id: number;
  min_momentum: number;
  exit_point: number;
  use_stop_loss: boolean;
  market_type: string;
  total_markets: number;
  trades_taken: number;
  entry_rate: number;
  wins: number;
  losses: number;
  stop_losses: number;
  win_rate: number;
  total_pnl: number;
  roi: number;
  avg_pnl_per_trade: number;
  avg_entry_price: number;
  avg_momentum: number;
  up_trades: number;
  down_trades: number;
}

export interface MomentumData {
  run: MomentumRun | null;
  results: MomentumResult[];
}

export async function getMomentumStrategyData(): Promise<MomentumData> {
  const runs = await query<Record<string, unknown>>(
    "SELECT * FROM momentum_strategy_runs ORDER BY ran_at DESC LIMIT 1"
  );

  if (runs.length === 0) {
    return { run: null, results: [] };
  }

  const run = runs[0];
  const runId = run.id as number;

  const rawResults = await query<Record<string, unknown>>(
    "SELECT * FROM momentum_strategy_results WHERE strategy_run_id = $1 ORDER BY total_pnl DESC",
    [runId]
  );

  const results: MomentumResult[] = rawResults.map((r) => ({
    id: Number(r.id),
    strategy_run_id: Number(r.strategy_run_id),
    min_momentum: parseFloat(String(r.min_momentum)),
    exit_point: parseFloat(String(r.exit_point)),
    use_stop_loss: r.use_stop_loss === true || r.use_stop_loss === "true" || r.use_stop_loss === "t",
    market_type: String(r.market_type),
    total_markets: Number(r.total_markets),
    trades_taken: Number(r.trades_taken),
    entry_rate: parseFloat(String(r.entry_rate)),
    wins: Number(r.wins),
    losses: Number(r.losses),
    stop_losses: Number(r.stop_losses),
    win_rate: parseFloat(String(r.win_rate)),
    total_pnl: parseFloat(String(r.total_pnl)),
    roi: parseFloat(String(r.roi)),
    avg_pnl_per_trade: parseFloat(String(r.avg_pnl_per_trade)),
    avg_entry_price: parseFloat(String(r.avg_entry_price)),
    avg_momentum: parseFloat(String(r.avg_momentum)),
    up_trades: Number(r.up_trades),
    down_trades: Number(r.down_trades),
  }));

  const parsedRun: MomentumRun = {
    id: Number(run.id),
    ran_at: String(run.ran_at),
    markets_tested: Number(run.markets_tested),
    total_combinations: Number(run.total_combinations),
    date_range_start: String(run.date_range_start),
    date_range_end: String(run.date_range_end),
  };

  return { run: parsedRun, results };
}
