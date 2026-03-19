# optimize_S1 Analysis

## Summary

- Configurations tested: 262144
- With trades: 262144
- Profitable: 9334
- Unprofitable: 252810

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S1_entry_window_start=20_entry_window_end=105_price_low_threshold=0.4_price_high_threshold=0.55_min_deviation=0.06_rebound_lookback=12_rebound_min_move=0.02_stop_loss=0.3_take_profit=0.65 |
| total_bets | 5529 |
| wins | 1533 |
| losses | 3996 |
| win_rate_pct | 27.73 |
| total_pnl | 7.1731 |
| avg_bet_pnl | 0.001297 |
| profit_factor | 1.0229 |
| expected_value | 0.001212 |
| total_entry_fees | 24.2281 |
| total_exit_fees | 20.2454 |
| total_fees | 44.4735 |
| sharpe_ratio | 0.0087 |
| sortino_ratio | 0.0225 |
| max_drawdown | 15.0682 |
| std_dev_pnl | 0.149533 |
| pct_profitable_assets | 75.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 98.23 |
| q1_pnl | 1.4449 |
| q2_pnl | -9.6263 |
| q3_pnl | 4.4741 |
| q4_pnl | 10.8804 |
| eligible_markets | 6481 |
| skipped_markets_missing_features | 0 |
| entry_window_start | 20 |
| entry_window_end | 105 |
| price_low_threshold | 0.4 |
| price_high_threshold | 0.55 |
| min_deviation | 0.06 |
| rebound_lookback | 12 |
| rebound_min_move | 0.02 |
| stop_loss | 0.3 |
| take_profit | 0.65 |
| ranking_score | 98.63 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 23.4271 | 2.7032 | 16.1400 | 38.0100 |
| total_pnl | -20.7167 | 12.5289 | -91.1405 | 19.2483 |
| avg_bet_pnl | -0.0038 | 0.0022 | -0.0141 | 0.0035 |
| sharpe_ratio | -0.0498 | 0.0476 | -0.2590 | 0.0209 |
| profit_factor | 0.8501 | 0.1450 | 0.3846 | 1.0638 |
| max_drawdown | 25.5982 | 10.8046 | 4.1986 | 93.0581 |
| consistency_score | 98.7943 | 0.4781 | 96.9600 | 99.9700 |
