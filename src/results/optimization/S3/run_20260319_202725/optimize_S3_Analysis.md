# optimize_S3 Analysis

## Summary

- Configurations tested: 17496
- With trades: 17496
- Profitable: 2308
- Unprofitable: 15188

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S3_spike_threshold=0.78_spike_lookback=30_reversion_pct=0.18_min_reversion_sec=60_entry_window_start=5_entry_window_end=240_min_seconds_since_extremum=3_min_distance_from_mid=0.08_stop_loss=0.2_take_profit=0.85 |
| total_bets | 3029 |
| wins | 730 |
| losses | 2299 |
| win_rate_pct | 24.1 |
| total_pnl | 15.1344 |
| avg_bet_pnl | 0.004996 |
| profit_factor | 1.0423 |
| expected_value | 0.004996 |
| total_entry_fees | 12.7294 |
| total_exit_fees | 4.2674 |
| total_fees | 16.9968 |
| sharpe_ratio | 0.0172 |
| sortino_ratio | 0.088 |
| max_drawdown | 13.9284 |
| std_dev_pnl | 0.291194 |
| pct_profitable_assets | 50.0 |
| pct_profitable_durations | 50.0 |
| consistency_score | 98.11 |
| q1_pnl | -2.3944 |
| q2_pnl | 16.1929 |
| q3_pnl | 2.0787 |
| q4_pnl | -0.7429 |
| eligible_markets | 8905 |
| skipped_markets_missing_features | 0 |
| spike_threshold | 0.78 |
| spike_lookback | 30 |
| reversion_pct | 0.18 |
| min_reversion_sec | 60 |
| entry_window_start | 5 |
| entry_window_end | 240 |
| min_seconds_since_extremum | 3 |
| min_distance_from_mid | 0.08 |
| stop_loss | 0.2 |
| take_profit | 0.85 |
| ranking_score | 92.66 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 21.0272 | 3.9751 | 12.5000 | 30.5600 |
| total_pnl | -11.6932 | 9.6735 | -34.7541 | 16.8369 |
| avg_bet_pnl | -0.0078 | 0.0069 | -0.0284 | 0.0065 |
| sharpe_ratio | -0.0286 | 0.0253 | -0.1052 | 0.0224 |
| profit_factor | 0.9337 | 0.0569 | 0.7703 | 1.0584 |
| max_drawdown | 19.9588 | 6.0755 | 8.9457 | 41.4671 |
| consistency_score | 98.1968 | 0.8582 | 95.6400 | 99.9600 |
