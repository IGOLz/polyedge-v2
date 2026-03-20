# optimize_S9 Analysis

## Summary

- Configurations tested: 786432
- With trades: 785984
- Profitable: 195904
- Unprofitable: 590080

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S9_compression_window=20_compression_max_std=0.008_compression_max_range=0.03_trigger_scan_start=30_trigger_scan_end=180_breakout_distance=0.03_momentum_lookback=15_efficiency_min=0.65_stop_loss=0.4_take_profit=0.7 |
| total_bets | 170 |
| wins | 119 |
| losses | 51 |
| win_rate_pct | 70.0 |
| total_pnl | 4.9662 |
| avg_bet_pnl | 0.029213 |
| profit_factor | 1.6164 |
| expected_value | 0.029213 |
| total_entry_fees | 1.401 |
| total_exit_fees | 1.1198 |
| total_fees | 2.5208 |
| sharpe_ratio | 0.2071 |
| sortino_ratio | 0.3278 |
| max_drawdown | 0.8003 |
| std_dev_pnl | 0.141062 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 96.0 |
| q1_pnl | 2.1632 |
| q2_pnl | 1.6686 |
| q3_pnl | -0.0928 |
| q4_pnl | 1.2273 |
| eligible_markets | 7600 |
| skipped_markets_missing_features | 0 |
| compression_window | 20 |
| compression_max_std | 0.008 |
| compression_max_range | 0.03 |
| trigger_scan_start | 30 |
| trigger_scan_end | 180 |
| breakout_distance | 0.03 |
| momentum_lookback | 15 |
| efficiency_min | 0.65 |
| stop_loss | 0.4 |
| take_profit | 0.7 |
| ranking_score | 90.37 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 51.7733 | 14.7721 | 0.0000 | 92.3100 |
| total_pnl | -1.9843 | 3.5965 | -31.1108 | 7.5096 |
| avg_bet_pnl | -0.0130 | 0.0287 | -0.4433 | 0.1430 |
| sharpe_ratio | -0.1533 | 1.8254 | -133.0230 | 1.6021 |
| profit_factor | 0.8589 | 2.0464 | 0.0000 | 254.7137 |
| max_drawdown | 2.9210 | 3.4551 | 0.0000 | 31.9113 |
| consistency_score | 88.5258 | 10.5234 | 50.0000 | 100.0000 |
