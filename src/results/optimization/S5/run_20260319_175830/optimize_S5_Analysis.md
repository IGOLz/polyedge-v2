# optimize_S5 Analysis

## Summary

- Configurations tested: 262144
- With trades: 262144
- Profitable: 106734
- Unprofitable: 155410

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S5_entry_window_start=60_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.47_price_range_high=0.58_approach_lookback=12_cross_buffer=0.02_stop_loss=0.3_take_profit=0.65 |
| total_bets | 580 |
| wins | 435 |
| losses | 145 |
| win_rate_pct | 75.0 |
| total_pnl | 15.3221 |
| avg_bet_pnl | 0.026417 |
| profit_factor | 1.4016 |
| expected_value | 0.026417 |
| total_entry_fees | 4.7803 |
| total_exit_fees | 3.8233 |
| total_fees | 8.6036 |
| sharpe_ratio | 0.1543 |
| sortino_ratio | 0.826 |
| max_drawdown | 2.0407 |
| std_dev_pnl | 0.171175 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.73 |
| q1_pnl | 5.6562 |
| q2_pnl | 5.176 |
| q3_pnl | 2.877 |
| q4_pnl | 1.6129 |
| eligible_markets | 6567 |
| skipped_markets_missing_features | 0 |
| entry_window_start | 60 |
| entry_window_end | 180 |
| allowed_hours | [18, 19, 20, 21, 22, 23] |
| price_range_low | 0.47 |
| price_range_high | 0.58 |
| approach_lookback | 12 |
| cross_buffer | 0.02 |
| stop_loss | 0.3 |
| take_profit | 0.65 |
| ranking_score | 96.63 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 61.2878 | 9.1700 | 33.3300 | 93.7500 |
| total_pnl | -3.3325 | 12.3586 | -72.2214 | 47.7049 |
| avg_bet_pnl | -0.0013 | 0.0130 | -0.0614 | 0.1104 |
| sharpe_ratio | -0.0124 | 0.0716 | -0.2910 | 0.6067 |
| profit_factor | 0.9797 | 0.1653 | 0.4835 | 4.1248 |
| max_drawdown | 10.2573 | 8.7534 | 0.1899 | 72.6529 |
| consistency_score | 96.7909 | 2.9604 | 67.1700 | 99.9700 |
