# optimize_S2 Analysis

## Summary

- Configurations tested: 196608
- With trades: 159744
- Profitable: 6816
- Unprofitable: 152928

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S2_eval_window_start=20_eval_window_end=30_momentum_threshold=0.03_tolerance=2_max_entry_second=90_efficiency_min=0.65_min_distance_from_mid=0.02_stop_loss=0.2_take_profit=0.8 |
| total_bets | 6429 |
| wins | 3980 |
| losses | 2449 |
| win_rate_pct | 61.91 |
| total_pnl | 15.5103 |
| avg_bet_pnl | 0.002413 |
| profit_factor | 1.0205 |
| expected_value | 0.002413 |
| total_entry_fees | 47.7041 |
| total_exit_fees | 20.8892 |
| total_fees | 68.5933 |
| sharpe_ratio | 0.0088 |
| sortino_ratio | 0.0162 |
| max_drawdown | 21.4946 |
| std_dev_pnl | 0.274632 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 99.48 |
| q1_pnl | -4.1489 |
| q2_pnl | 1.2136 |
| q3_pnl | 7.0592 |
| q4_pnl | 11.3864 |
| eligible_markets | 6508 |
| skipped_markets_missing_features | 0 |
| eval_window_start | 20 |
| eval_window_end | 30 |
| momentum_threshold | 0.03 |
| tolerance | 2 |
| max_entry_second | 90 |
| efficiency_min | 0.65 |
| min_distance_from_mid | 0.02 |
| stop_loss | 0.2 |
| take_profit | 0.8 |
| ranking_score | 98.73 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 46.1146 | 10.1510 | 18.6400 | 69.4400 |
| total_pnl | -22.7819 | 17.3477 | -94.0393 | 20.5900 |
| avg_bet_pnl | -0.0087 | 0.0062 | -0.0819 | 0.0274 |
| sharpe_ratio | -0.0678 | 0.0481 | -0.3712 | 0.2571 |
| profit_factor | 0.7927 | 0.1630 | 0.1737 | 2.7249 |
| max_drawdown | 25.5277 | 17.5209 | 0.2490 | 94.1086 |
| consistency_score | 96.3162 | 3.3755 | 75.7400 | 99.9700 |
