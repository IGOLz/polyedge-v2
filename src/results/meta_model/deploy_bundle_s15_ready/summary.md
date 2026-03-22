# Meta-Model Selector

## Summary

- Dataset rows: 3986
- Dataset markets: 3986
- Experts: S15
- Splits: 2
- Min threshold: 0.000000
- Top K per day: off
- Top percent per day: off

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 1077 | 1217 |
| win_rate_pct | 66.11 | 64.59 |
| total_pnl | 26.3067 | 26.9598 |
| profit_factor | 1.8105 | 1.7983 |
| sharpe_ratio | 0.1999 | 0.1911 |
| max_drawdown | 1.6726 | 1.8561 |

## Retention

| Metric | Value |
| --- | --- |
| trade_retain_pct | 88.5 |
| pnl_retain_pct | 97.58 |
| pnl_delta | -0.6531 |
| profit_factor_delta | 0.0122 |
| sharpe_delta | 0.0088 |
| max_drawdown_delta | -0.1835 |


## Deployment Recommendation

- Recommended deploy threshold: 0.011135
- Pooled OOS trades retained: 88.5%
- Pooled OOS pnl retained: 97.58%
- Pooled OOS pnl delta: -0.6531
- Pooled OOS PF delta: 0.0122


## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: 0.011135
- Effective threshold: 0.011135
- Policy rows: threshold 621 -> selected 621

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 759 | 24.07 | 2.0562 | 0.2541 | 1.4986 |
| Test Selector | 621 | 11.1608 | 1.5509 | 0.146 | 1.2293 |
| Test All Signals | 646 | 11.4112 | 1.5572 | 0.1462 | 1.2136 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 96.13 |
| pnl_retain_pct | 97.81 |
| pnl_delta | -0.2504 |
| profit_factor_delta | -0.0063 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.011425
- Effective threshold: 0.011425
- Policy rows: threshold 456 -> selected 456

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 518 | 10.1872 | 1.4967 | 0.1428 | 2.7372 |
| Test Selector | 456 | 15.1459 | 2.2416 | 0.2755 | 1.6726 |
| Test All Signals | 571 | 15.5486 | 2.1697 | 0.2476 | 1.8561 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 79.86 |
| pnl_retain_pct | 97.41 |
| pnl_delta | -0.4027 |
| profit_factor_delta | 0.0719 |
