# optimize_S10 Analysis

## Summary

- Configurations tested: 921600
- With trades: 860975
- Profitable: 60729
- Unprofitable: 800246

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S10_impulse_start=10_impulse_end=45_impulse_threshold=0.1_retrace_window=10_retrace_min=0.1_retrace_max=0.35_reacceleration_threshold=0.01_impulse_efficiency_min=0.55_stop_loss=0.25_take_profit=0.8 |
| total_bets | 289 |
| wins | 212 |
| losses | 77 |
| win_rate_pct | 73.36 |
| total_pnl | 5.5963 |
| avg_bet_pnl | 0.019364 |
| profit_factor | 1.3211 |
| expected_value | 0.019364 |
| total_entry_fees | 2.0341 |
| total_exit_fees | 1.1892 |
| total_fees | 3.2233 |
| sharpe_ratio | 0.1002 |
| sortino_ratio | 0.0914 |
| max_drawdown | 1.6236 |
| std_dev_pnl | 0.193269 |
| pct_profitable_assets | 75.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 97.73 |
| q1_pnl | 0.4005 |
| q2_pnl | 1.4254 |
| q3_pnl | 0.5462 |
| q4_pnl | 3.2242 |
| eligible_markets | 11312 |
| skipped_markets_missing_features | 0 |
| impulse_start | 10 |
| impulse_end | 45 |
| impulse_threshold | 0.1 |
| retrace_window | 10 |
| retrace_min | 0.1 |
| retrace_max | 0.35 |
| reacceleration_threshold | 0.01 |
| impulse_efficiency_min | 0.55 |
| stop_loss | 0.25 |
| take_profit | 0.8 |
| ranking_score | 91.81 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 34.5147 | 17.7456 | 0.0000 | 100.0000 |
| total_pnl | -3.2454 | 3.9647 | -39.6124 | 7.9535 |
| avg_bet_pnl | -0.0249 | 0.0301 | -0.4648 | 0.2628 |
| sharpe_ratio | -0.9879 | 15.8533 | -464.8410 | 262.7680 |
| profit_factor | 1.0741 | 17.4024 | 0.0000 | 3044.4525 |
| max_drawdown | 3.7259 | 4.1029 | 0.0000 | 40.0386 |
| consistency_score | 89.5412 | 10.4896 | 50.0000 | 100.0000 |
