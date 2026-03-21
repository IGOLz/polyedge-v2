# optimize_S14 Analysis

## Summary

- Configurations tested: 393216
- With trades: 393216
- Profitable: 180548
- Unprofitable: 212668

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S14_feature_window=30_entry_window_start=45_entry_window_end=240_min_market_delta_abs=0.06_max_underlying_return_abs=0.0015_extreme_price_low=0.25_extreme_price_high=0.65_require_direction_mismatch=True_stop_loss=0.3_take_profit=0.7 |
| total_bets | 3564 |
| wins | 986 |
| losses | 2578 |
| win_rate_pct | 27.67 |
| total_pnl | 44.8164 |
| avg_bet_pnl | 0.012575 |
| profit_factor | 1.7236 |
| expected_value | 0.012377 |
| total_entry_fees | 5.9607 |
| total_exit_fees | 6.0246 |
| total_fees | 11.9853 |
| sharpe_ratio | 0.1221 |
| sortino_ratio | 0.4412 |
| max_drawdown | 1.6474 |
| std_dev_pnl | 0.10297 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 50.0 |
| consistency_score | 96.84 |
| q1_pnl | 7.7727 |
| q2_pnl | 15.2572 |
| q3_pnl | 6.224 |
| q4_pnl | 15.5625 |
| eligible_markets | 10661 |
| skipped_markets_missing_features | 991 |
| feature_window | 30 |
| entry_window_start | 45 |
| entry_window_end | 240 |
| min_market_delta_abs | 0.06 |
| max_underlying_return_abs | 0.0015 |
| extreme_price_low | 0.25 |
| extreme_price_high | 0.65 |
| require_direction_mismatch | True |
| stop_loss | 0.3 |
| take_profit | 0.7 |
| ranking_score | 87.84 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 20.0041 | 6.8572 | 5.9300 | 39.6200 |
| total_pnl | -46.6523 | 65.1462 | -261.1564 | 74.3872 |
| avg_bet_pnl | -0.0049 | 0.0101 | -0.0254 | 0.0262 |
| sharpe_ratio | -0.0983 | 0.1900 | -0.6803 | 0.2113 |
| profit_factor | 0.8693 | 0.4212 | 0.1375 | 2.5570 |
| max_drawdown | 53.6214 | 59.3215 | 0.1811 | 263.7894 |
| consistency_score | 98.5395 | 1.0232 | 89.4900 | 99.9900 |
