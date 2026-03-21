# optimize_S15 Analysis

## Summary

- Configurations tested: 786432
- With trades: 786432
- Profitable: 589070
- Unprofitable: 197362

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S15_setup_window_end=20_breakout_scan_start=25_breakout_scan_end=240_breakout_buffer=0.01_confirmation_points=4_feature_window=5_min_underlying_return=0.0005_min_trade_count=40.0_stop_loss=0.35_take_profit=0.75 |
| total_bets | 4882 |
| wins | 3219 |
| losses | 1663 |
| win_rate_pct | 65.94 |
| total_pnl | 102.0663 |
| avg_bet_pnl | 0.020907 |
| profit_factor | 1.6913 |
| expected_value | 0.020351 |
| total_entry_fees | 29.2096 |
| total_exit_fees | 21.8008 |
| total_fees | 51.0104 |
| sharpe_ratio | 0.1747 |
| sortino_ratio | 0.1626 |
| max_drawdown | 3.5016 |
| std_dev_pnl | 0.119693 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.75 |
| q1_pnl | 38.0897 |
| q2_pnl | 24.4573 |
| q3_pnl | 25.9524 |
| q4_pnl | 13.5669 |
| eligible_markets | 10680 |
| skipped_markets_missing_features | 1056 |
| setup_window_end | 20 |
| breakout_scan_start | 25 |
| breakout_scan_end | 240 |
| breakout_buffer | 0.01 |
| confirmation_points | 4 |
| feature_window | 5 |
| min_underlying_return | 0.0005 |
| min_trade_count | 40.0 |
| stop_loss | 0.35 |
| take_profit | 0.75 |
| ranking_score | 88.49 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 53.1629 | 7.5295 | 21.0500 | 73.5200 |
| total_pnl | 4.0084 | 18.4411 | -90.0757 | 122.9146 |
| avg_bet_pnl | 0.0067 | 0.0094 | -0.0610 | 0.0468 |
| sharpe_ratio | 0.0840 | 0.1210 | -0.3422 | 0.6315 |
| profit_factor | 1.5212 | 0.8952 | 0.1357 | 13.2927 |
| max_drawdown | 9.1030 | 13.3126 | 0.0391 | 91.1726 |
| consistency_score | 95.7513 | 4.3074 | 62.8600 | 100.0000 |
