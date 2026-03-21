# optimize_S11 Analysis

## Summary

- Configurations tested: 307200
- With trades: 307200
- Profitable: 1
- Unprofitable: 307199

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S11_precondition_window=45_extreme_deviation=0.08_reclaim_scan_start=65_reclaim_scan_end=180_hold_seconds=2_hold_buffer=0.015_post_reclaim_move=0.03_stop_loss=0.3_take_profit=0.8 |
| total_bets | 4432 |
| wins | 2674 |
| losses | 1758 |
| win_rate_pct | 60.33 |
| total_pnl | -21.3223 |
| avg_bet_pnl | -0.004811 |
| profit_factor | 0.9615 |
| expected_value | -0.004811 |
| total_entry_fees | 37.0333 |
| total_exit_fees | 16.6071 |
| total_fees | 53.6404 |
| sharpe_ratio | -0.0185 |
| sortino_ratio | -0.063 |
| max_drawdown | 36.4014 |
| std_dev_pnl | 0.259974 |
| pct_profitable_assets | 25.0 |
| pct_profitable_durations | 0.0 |
| consistency_score | 98.29 |
| q1_pnl | -14.4319 |
| q2_pnl | 19.4829 |
| q3_pnl | -29.6077 |
| q4_pnl | 3.2344 |
| eligible_markets | 11490 |
| skipped_markets_missing_features | 0 |
| precondition_window | 45 |
| extreme_deviation | 0.08 |
| reclaim_scan_start | 65 |
| reclaim_scan_end | 180 |
| hold_seconds | 2 |
| hold_buffer | 0.015 |
| post_reclaim_move | 0.03 |
| stop_loss | 0.3 |
| take_profit | 0.8 |
| ranking_score | 91.53 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 56.1875 | 7.7926 | 30.1700 | 76.9400 |
| total_pnl | -52.4543 | 24.7011 | -158.3644 | 0.5229 |
| avg_bet_pnl | -0.0197 | 0.0048 | -0.0426 | 0.0012 |
| sharpe_ratio | -0.1354 | 0.0729 | -0.4519 | 0.0065 |
| profit_factor | 0.7145 | 0.1618 | 0.2221 | 1.0155 |
| max_drawdown | 54.5084 | 24.3906 | 3.5086 | 158.3794 |
| consistency_score | 98.1899 | 0.8737 | 92.1300 | 99.9800 |
