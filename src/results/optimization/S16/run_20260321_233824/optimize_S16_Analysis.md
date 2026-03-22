# optimize_S16 Analysis

## Summary

- Configurations tested: 262144
- With trades: 196608
- Profitable: 34984
- Unprofitable: 161624

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S16_short_window=5_long_window=30_entry_window_start=20_entry_window_end=240_min_short_return=0.0015_min_long_return_opposite=0.0015_min_price_distance_from_mid=0.1_max_underlying_vol=0.016_stop_loss=0.3_take_profit=0.75 |
| total_bets | 51 |
| wins | 21 |
| losses | 30 |
| win_rate_pct | 41.18 |
| total_pnl | 2.1439 |
| avg_bet_pnl | 0.042037 |
| profit_factor | 4.705 |
| expected_value | 0.042037 |
| total_entry_fees | 0.0677 |
| total_exit_fees | 0.0784 |
| total_fees | 0.1461 |
| sharpe_ratio | 0.3057 |
| sortino_ratio | 1.9539 |
| max_drawdown | 0.2059 |
| std_dev_pnl | 0.137522 |
| pct_profitable_assets | 75.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 82.42 |
| q1_pnl | -0.1291 |
| q2_pnl | 0.7671 |
| q3_pnl | -0.0154 |
| q4_pnl | 1.5213 |
| eligible_markets | 10680 |
| skipped_markets_missing_features | 1472 |
| short_window | 5 |
| long_window | 30 |
| entry_window_start | 20 |
| entry_window_end | 240 |
| min_short_return | 0.0015 |
| min_long_return_opposite | 0.0015 |
| min_price_distance_from_mid | 0.1 |
| max_underlying_vol | 0.016 |
| stop_loss | 0.3 |
| take_profit | 0.75 |
| ranking_score | 87.95 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 20.2404 | 13.2760 | 0.0000 | 60.0000 |
| total_pnl | -0.4130 | 1.0819 | -9.9926 | 4.6114 |
| avg_bet_pnl | -0.0098 | 0.0287 | -0.1133 | 0.2031 |
| sharpe_ratio | -1.0369 | 2.6905 | -10.4402 | 0.7920 |
| profit_factor | 1.0131 | 2.7593 | 0.0000 | 33.6339 |
| max_drawdown | 0.8678 | 1.2298 | 0.0100 | 10.4928 |
| consistency_score | 82.0949 | 16.0955 | 50.0000 | 100.0000 |
