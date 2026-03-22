# Meta-Model Selector

## Summary

- Dataset rows: 8051
- Dataset markets: 6025
- Experts: S5, S13, S14, S15
- Splits: 2
- Min threshold: 0.000000
- Top K per day: off
- Top percent per day: off

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 1610 | 2272 |
| win_rate_pct | 57.58 | 46.52 |
| total_pnl | 48.4983 | 51.0878 |
| profit_factor | 1.9552 | 1.7182 |
| sharpe_ratio | 0.2068 | 0.1572 |
| max_drawdown | 2.0364 | 2.2311 |

## Retention

| Metric | Value |
| --- | --- |
| trade_retain_pct | 70.86 |
| pnl_retain_pct | 94.93 |
| pnl_delta | -2.5895 |
| profit_factor_delta | 0.237 |
| sharpe_delta | 0.0496 |
| max_drawdown_delta | -0.1947 |


## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: 0.022337
- Effective threshold: 0.022337
- Policy rows: threshold 907 -> selected 907

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 1116 | 36.5568 | 2.038 | 0.2264 | 1.1689 |
| Test Selector | 907 | 18.5373 | 1.5909 | 0.1446 | 1.3345 |
| Test All Signals | 1157 | 17.4068 | 1.4362 | 0.1087 | 1.5485 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 78.39 |
| pnl_retain_pct | 106.49 |
| pnl_delta | 1.1305 |
| profit_factor_delta | 0.1547 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.018625
- Effective threshold: 0.018625
- Policy rows: threshold 703 -> selected 703

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 793 | 13.4657 | 1.4226 | 0.115 | 2.1896 |
| Test Selector | 703 | 29.9611 | 2.5443 | 0.2837 | 2.0364 |
| Test All Signals | 1115 | 33.681 | 2.0785 | 0.2049 | 2.2311 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 63.05 |
| pnl_retain_pct | 88.96 |
| pnl_delta | -3.7199 |
| profit_factor_delta | 0.4658 |
