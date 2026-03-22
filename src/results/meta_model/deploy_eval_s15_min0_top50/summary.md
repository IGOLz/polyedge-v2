# Meta-Model Selector

## Summary

- Dataset rows: 3986
- Dataset markets: 3986
- Experts: S5, S13, S14, S15
- Splits: 2
- Min threshold: 0.000000
- Top K per day: off
- Top percent per day: 0.5

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 539 | 1217 |
| win_rate_pct | 76.25 | 64.59 |
| total_pnl | 21.2955 | 26.9598 |
| profit_factor | 1.7528 | 1.7983 |
| sharpe_ratio | 0.2379 | 0.1911 |
| max_drawdown | 1.6605 | 1.8561 |

## Retention

| Metric | Value |
| --- | --- |
| trade_retain_pct | 44.29 |
| pnl_retain_pct | 78.99 |
| pnl_delta | -5.6643 |
| profit_factor_delta | -0.0455 |
| sharpe_delta | 0.0468 |
| max_drawdown_delta | -0.1956 |


## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: 0.011135
- Effective threshold: 0.011135
- Policy rows: threshold 621 -> selected 311

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 380 | 18.2815 | 2.0341 | 0.3039 | 1.5701 |
| Test Selector | 311 | 7.9035 | 1.4524 | 0.1529 | 1.1844 |
| Test All Signals | 646 | 11.4112 | 1.5572 | 0.1462 | 1.2136 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 48.14 |
| pnl_retain_pct | 69.26 |
| pnl_delta | -3.5077 |
| profit_factor_delta | -0.1048 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.011425
- Effective threshold: 0.011425
- Policy rows: threshold 456 -> selected 228

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 259 | 8.8023 | 1.5631 | 0.1928 | 1.8942 |
| Test Selector | 228 | 13.3921 | 2.2382 | 0.3574 | 1.6605 |
| Test All Signals | 571 | 15.5486 | 2.1697 | 0.2476 | 1.8561 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 39.93 |
| pnl_retain_pct | 86.13 |
| pnl_delta | -2.1565 |
| profit_factor_delta | 0.0685 |
