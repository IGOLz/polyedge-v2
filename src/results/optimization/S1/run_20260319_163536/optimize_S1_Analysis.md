# optimize_S1 Analysis

## Summary

- Configurations tested: 34992
- With trades: 34992
- Profitable: 1852
- Unprofitable: 33140

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S1_entry_window_start=20_entry_window_end=90_price_low_threshold=0.41_price_high_threshold=0.57_min_deviation=0.07_rebound_lookback=12_rebound_min_move=0.012_stop_loss=0.28_take_profit=0.8 |
| total_bets | 6295 |
| wins | 1391 |
| losses | 4904 |
| win_rate_pct | 22.1 |
| total_pnl | 8.4989 |
| avg_bet_pnl | 0.00135 |
| profit_factor | 1.0186 |
| expected_value | 0.001321 |
| total_entry_fees | 28.0265 |
| total_exit_fees | 16.9402 |
| total_fees | 44.9667 |
| sharpe_ratio | 0.0067 |
| sortino_ratio | 0.0236 |
| max_drawdown | 12.7446 |
| std_dev_pnl | 0.200526 |
| pct_profitable_assets | 50.0 |
| pct_profitable_durations | 50.0 |
| consistency_score | 98.79 |
| q1_pnl | -1.3716 |
| q2_pnl | 0.8092 |
| q3_pnl | 0.9491 |
| q4_pnl | 8.1122 |
| eligible_markets | 8665 |
| skipped_markets_missing_features | 0 |
| entry_window_start | 20 |
| entry_window_end | 90 |
| price_low_threshold | 0.41 |
| price_high_threshold | 0.57 |
| min_deviation | 0.07 |
| rebound_lookback | 12 |
| rebound_min_move | 0.012 |
| stop_loss | 0.28 |
| take_profit | 0.8 |
| ranking_score | 97.79 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 20.4884 | 1.5277 | 17.2500 | 25.2900 |
| total_pnl | -14.3708 | 8.9249 | -47.5306 | 13.9699 |
| avg_bet_pnl | -0.0021 | 0.0013 | -0.0063 | 0.0020 |
| sharpe_ratio | -0.0136 | 0.0085 | -0.0370 | 0.0110 |
| profit_factor | 0.9615 | 0.0235 | 0.8927 | 1.0330 |
| max_drawdown | 25.4583 | 7.3829 | 9.8064 | 57.5279 |
| consistency_score | 99.1179 | 0.2386 | 98.3600 | 99.8900 |
