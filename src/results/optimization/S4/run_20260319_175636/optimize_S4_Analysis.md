# optimize_S4 Analysis

## Summary

- Configurations tested: 512000
- With trades: 509056
- Profitable: 155853
- Unprofitable: 353203

## Best Configuration (by ranking score)

| Metric | Value |
|--------|-------|
| config_id | S4_lookback_window=30_vol_threshold=0.03_eval_second=20_extreme_price_low=0.2_extreme_price_high=0.8_reversal_lookback=3_reversal_min_move=0.008_stop_loss=0.2_take_profit=0.7 |
| total_bets | 6 |
| wins | 3 |
| losses | 3 |
| win_rate_pct | 50.0 |
| total_pnl | 1.0585 |
| avg_bet_pnl | 0.176411 |
| profit_factor | 136.701 |
| expected_value | 0.176411 |
| total_entry_fees | 0.0064 |
| total_exit_fees | 0.019 |
| total_fees | 0.0254 |
| sharpe_ratio | 0.6555 |
| sortino_ratio | 0.0 |
| max_drawdown | 0.0026 |
| std_dev_pnl | 0.26913 |
| pct_profitable_assets | 100.0 |
| pct_profitable_durations | 100.0 |
| consistency_score | 100.0 |
| q1_pnl | -0.0026 |
| q2_pnl | 0.0189 |
| q3_pnl | -0.0026 |
| q4_pnl | 1.0447 |
| eligible_markets | 6565 |
| skipped_markets_missing_features | 0 |
| lookback_window | 30 |
| vol_threshold | 0.03 |
| eval_second | 20 |
| extreme_price_low | 0.2 |
| extreme_price_high | 0.8 |
| reversal_lookback | 3 |
| reversal_min_move | 0.008 |
| stop_loss | 0.2 |
| take_profit | 0.7 |
| ranking_score | 97.92 |

## Metrics Distribution (configs with trades)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| win_rate_pct | 22.5265 | 12.3001 | 0.0000 | 100.0000 |
| total_pnl | -0.2844 | 1.0393 | -12.7833 | 12.3138 |
| avg_bet_pnl | -0.0038 | 0.0200 | -0.1812 | 0.3036 |
| sharpe_ratio | -0.2847 | 3.0513 | -181.2000 | 58.6762 |
| profit_factor | 1.1555 | 5.2642 | 0.0000 | 484.4590 |
| max_drawdown | 0.9632 | 1.1544 | 0.0000 | 16.7457 |
| consistency_score | 87.8793 | 11.6648 | 50.0000 | 100.0000 |
