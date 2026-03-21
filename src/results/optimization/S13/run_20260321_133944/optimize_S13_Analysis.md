# optimize_S13 Analysis

## Summary

- Configurations tested: 786432
- With trades: 786432
- Profitable: 741248
- Unprofitable: 45184

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S13_feature_window=5_entry_window_start=20_entry_window_end=240_min_underlying_return=0.001_min_market_confirmation=0.0_max_market_delta=0.05_max_price_distance_from_mid=0.2_max_underlying_vol=0.006_stop_loss=0.25_take_profit=0.75 |
| total_bets | 218 |
| wins | 204 |
| losses | 14 |
| win_rate_pct | 93.58 |
| total_pnl | 22.7322 |
| avg_bet_pnl | 0.104276 |
| profit_factor | 5.6835 |
| expected_value | 0.104276 |
| total_entry_fees | 1.8038 |
| total_exit_fees | 1.22 |
| total_fees | 3.0238 |
| sharpe_ratio | 0.7852 |
| sortino_ratio | 2.5998 |
| max_drawdown | 0.7054 |
| std_dev_pnl | 0.132795 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 97.76 |
| q1_pnl | 6.0162 |
| q2_pnl | 4.7404 |
| q3_pnl | 4.8063 |
| q4_pnl | 7.1693 |
| eligible_markets | 7632 |
| skipped_markets_missing_features | 3880 |
| feature_window | 5 |
| entry_window_start | 20 |
| entry_window_end | 240 |
| min_underlying_return | 0.001 |
| min_market_confirmation | 0.0 |
| max_market_delta | 0.05 |
| max_price_distance_from_mid | 0.2 |
| max_underlying_vol | 0.006 |
| stop_loss | 0.25 |
| take_profit | 0.75 |
| ranking_score | 82.06 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 79.2511 | 12.5923 | 0.0000 | 100.0000 |
| total_pnl | 9.3582 | 13.2609 | -3.6971 | 107.1040 |
| avg_bet_pnl | 0.0516 | 0.0542 | -0.4039 | 0.2630 |
| sharpe_ratio | -0.4929 | 26.2516 | -403.8690 | 262.9960 |
| profit_factor | 49.8431 | 206.6111 | 0.0000 | 4318.5250 |
| max_drawdown | 1.8025 | 2.4146 | 0.0000 | 19.8097 |
| consistency_score | 86.6786 | 13.7591 | 50.0000 | 100.0000 |
