# Meta-Model Selector

## Summary

- Dataset rows: 9182
- Dataset markets: 6400
- Experts: S5, S13, S14, S15
- Splits: 3

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 2388 | 2669 |
| win_rate_pct | 53.02 | 48.89 |
| total_pnl | 55.4429 | 55.7596 |
| profit_factor | 1.552 | 1.5282 |
| sharpe_ratio | 0.1485 | 0.1379 |
| max_drawdown | 2.3955 | 2.5218 |

## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: -0.005418

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 1600 | 46.9585 | 1.8449 | 0.1991 | 1.9172 |
| Test Selector | 1312 | 21.9011 | 1.4278 | 0.1161 | 2.3583 |
| Test All Signals | 1312 | 21.9011 | 1.4278 | 0.1161 | 2.3583 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.009910

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 1099 | 16.1995 | 1.303 | 0.0934 | 2.9872 |
| Test Selector | 974 | 32.0381 | 1.8063 | 0.1991 | 1.977 |
| Test All Signals | 1255 | 32.3548 | 1.7213 | 0.168 | 2.2311 |

### Split 3

- Train days: 2026-03-16, 2026-03-17, 2026-03-18
- Validation days: 2026-03-19
- Embargo days: 2026-03-20
- Test days: 2026-03-21
- Chosen threshold: 0.002667

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 927 | 27.2865 | 1.8759 | 0.205 | 1.3684 |
| Test Selector | 102 | 1.5037 | 1.1582 | 0.0697 | 2.3955 |
| Test All Signals | 102 | 1.5037 | 1.1582 | 0.0697 | 2.3955 |
