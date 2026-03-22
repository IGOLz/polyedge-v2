# Meta-Model Selector

## Summary

- Dataset rows: 3986
- Dataset markets: 3986
- Experts: S15
- Splits: 2

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 1064 | 1217 |
| win_rate_pct | 67.76 | 64.59 |
| total_pnl | 26.6379 | 26.9598 |
| profit_factor | 1.8073 | 1.7983 |
| sharpe_ratio | 0.2027 | 0.1911 |
| max_drawdown | 1.8441 | 1.8561 |

## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: -0.020442

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 782 | 24.4245 | 2.0636 | 0.2536 | 1.4986 |
| Test Selector | 646 | 11.4112 | 1.5572 | 0.1462 | 1.2136 |
| Test All Signals | 646 | 11.4112 | 1.5572 | 0.1462 | 1.2136 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.013593

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 518 | 9.8232 | 1.4503 | 0.133 | 2.5325 |
| Test Selector | 418 | 15.2267 | 2.2165 | 0.2871 | 1.8441 |
| Test All Signals | 571 | 15.5486 | 2.1697 | 0.2476 | 1.8561 |
