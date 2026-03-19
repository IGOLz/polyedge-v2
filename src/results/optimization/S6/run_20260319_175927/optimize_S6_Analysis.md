# optimize_S6 Analysis

## Summary

- Configurations tested: 61440
- With trades: 61440
- Profitable: 947
- Unprofitable: 60493

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S6_streak_length=4_streak_direction_filter=Up_entry_window_start=10_entry_window_end=30_price_floor=0.3_price_ceiling=0.7_stop_loss=0.2_take_profit=0.7 |
| total_bets | 408 |
| wins | 262 |
| losses | 146 |
| win_rate_pct | 64.22 |
| total_pnl | 2.0876 |
| avg_bet_pnl | 0.005117 |
| profit_factor | 1.0471 |
| expected_value | 0.005117 |
| total_entry_fees | 3.1225 |
| total_exit_fees | 2.055 |
| total_fees | 5.1775 |
| sharpe_ratio | 0.0209 |
| sortino_ratio | 0.0636 |
| max_drawdown | 8.2016 |
| std_dev_pnl | 0.244581 |
| pct_profitable_assets | 50.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.29 |
| q1_pnl | 3.1336 |
| q2_pnl | -3.3058 |
| q3_pnl | -1.6181 |
| q4_pnl | 3.8779 |
| eligible_markets | 6567 |
| skipped_markets_missing_features | 0 |
| streak_length | 4 |
| streak_direction_filter | Up |
| entry_window_start | 10 |
| entry_window_end | 30 |
| price_floor | 0.3 |
| price_ceiling | 0.7 |
| stop_loss | 0.2 |
| take_profit | 0.7 |
| ranking_score | 98.93 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 54.1423 | 6.1005 | 38.2900 | 72.3300 |
| total_pnl | -20.2232 | 21.3421 | -101.6946 | 6.1788 |
| avg_bet_pnl | -0.0256 | 0.0116 | -0.0626 | 0.0151 |
| sharpe_ratio | -0.1379 | 0.0695 | -0.4015 | 0.0549 |
| profit_factor | 0.7315 | 0.1282 | 0.3536 | 1.1235 |
| max_drawdown | 22.6243 | 21.0862 | 1.6195 | 104.1336 |
| consistency_score | 96.1897 | 2.8338 | 84.1300 | 99.9400 |
