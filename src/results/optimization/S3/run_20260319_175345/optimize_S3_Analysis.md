# optimize_S3 Analysis

## Summary

- Configurations tested: 1296
- With trades: 1296
- Profitable: 910
- Unprofitable: 386

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S3_spike_threshold=0.8_spike_lookback=15_reversion_pct=0.15_min_reversion_sec=60_stop_loss=0.15_take_profit=0.85 |
| total_bets | 3710 |
| wins | 899 |
| losses | 2811 |
| win_rate_pct | 24.23 |
| total_pnl | 54.7483 |
| avg_bet_pnl | 0.014757 |
| profit_factor | 1.1205 |
| expected_value | 0.014757 |
| total_entry_fees | 11.4913 |
| total_exit_fees | 3.1993 |
| total_fees | 14.6906 |
| sharpe_ratio | 0.0462 |
| sortino_ratio | 0.2239 |
| max_drawdown | 12.048 |
| std_dev_pnl | 0.319192 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.98 |
| q1_pnl | 3.6953 |
| q2_pnl | 32.596 |
| q3_pnl | 7.6872 |
| q4_pnl | 10.7698 |
| eligible_markets | 6565 |
| skipped_markets_missing_features | 0 |
| spike_threshold | 0.8 |
| spike_lookback | 15 |
| reversion_pct | 0.15 |
| min_reversion_sec | 60 |
| stop_loss | 0.15 |
| take_profit | 0.85 |
| ranking_score | 96.68 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 21.4041 | 4.0098 | 13.5400 | 34.1700 |
| total_pnl | 9.8490 | 19.4044 | -42.0940 | 62.4732 |
| avg_bet_pnl | 0.0025 | 0.0043 | -0.0079 | 0.0170 |
| sharpe_ratio | 0.0109 | 0.0181 | -0.0261 | 0.0626 |
| profit_factor | 1.0367 | 0.0592 | 0.8981 | 1.2017 |
| max_drawdown | 20.4964 | 12.9455 | 5.2627 | 56.6085 |
| consistency_score | 99.0499 | 0.4358 | 97.0600 | 99.7100 |
