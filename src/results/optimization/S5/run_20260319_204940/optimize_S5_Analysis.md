# optimize_S5 Analysis

## Summary

- Configurations tested: 6144
- With trades: 6144
- Profitable: 2536
- Unprofitable: 3608

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S5_entry_window_start=45_entry_window_end=240_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.015_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7 |
| total_bets | 1089 |
| wins | 691 |
| losses | 398 |
| win_rate_pct | 63.45 |
| total_pnl | 18.6333 |
| avg_bet_pnl | 0.01711 |
| profit_factor | 1.2114 |
| expected_value | 0.01711 |
| total_entry_fees | 9.076 |
| total_exit_fees | 6.531 |
| total_fees | 15.607 |
| sharpe_ratio | 0.0929 |
| sortino_ratio | 0.5403 |
| max_drawdown | 4.8155 |
| std_dev_pnl | 0.184147 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.79 |
| q1_pnl | 5.6624 |
| q2_pnl | 8.6887 |
| q3_pnl | 6.4969 |
| q4_pnl | -2.2148 |
| eligible_markets | 8934 |
| skipped_markets_missing_features | 0 |
| entry_window_start | 45 |
| entry_window_end | 240 |
| allowed_hours | [18, 19, 20, 21, 22, 23] |
| price_range_low | 0.45 |
| price_range_high | 0.6 |
| approach_lookback | 12 |
| cross_buffer | 0.015 |
| confirmation_lookback | 5 |
| confirmation_min_move | 0.01 |
| min_cross_move | 0.04 |
| stop_loss | 0.35 |
| take_profit | 0.7 |
| ranking_score | 85.76 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 64.7264 | 4.2986 | 55.7700 | 74.0900 |
| total_pnl | -12.2532 | 21.4227 | -73.0601 | 18.8353 |
| avg_bet_pnl | -0.0021 | 0.0090 | -0.0164 | 0.0203 |
| sharpe_ratio | -0.0124 | 0.0503 | -0.0912 | 0.1117 |
| profit_factor | 0.9778 | 0.1078 | 0.8130 | 1.2585 |
| max_drawdown | 20.0271 | 17.9439 | 2.5182 | 73.2926 |
| consistency_score | 97.9665 | 0.8889 | 95.2900 | 99.9100 |
