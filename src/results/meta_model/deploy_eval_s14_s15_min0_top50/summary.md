# Meta-Model Selector

## Summary

- Dataset rows: 8051
- Dataset markets: 6025
- Experts: S5, S13, S14, S15
- Splits: 2
- Min threshold: 0.000000
- Top K per day: off
- Top percent per day: 0.5

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 806 | 2272 |
| win_rate_pct | 57.57 | 46.52 |
| total_pnl | 27.8551 | 51.0878 |
| profit_factor | 1.8665 | 1.7182 |
| sharpe_ratio | 0.215 | 0.1572 |
| max_drawdown | 1.7932 | 2.2311 |

## Retention

| Metric | Value |
| --- | --- |
| trade_retain_pct | 35.48 |
| pnl_retain_pct | 54.52 |
| pnl_delta | -23.2327 |
| profit_factor_delta | 0.1483 |
| sharpe_delta | 0.0578 |
| max_drawdown_delta | -0.4379 |


## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: 0.022337
- Effective threshold: 0.022337
- Policy rows: threshold 907 -> selected 454

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 558 | 19.357 | 2.0522 | 0.2326 | 0.9212 |
| Test Selector | 454 | 7.3496 | 1.4289 | 0.1142 | 1.4363 |
| Test All Signals | 1157 | 17.4068 | 1.4362 | 0.1087 | 1.5485 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 39.24 |
| pnl_retain_pct | 42.22 |
| pnl_delta | -10.0572 |
| profit_factor_delta | -0.0073 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.018625
- Effective threshold: 0.018625
- Policy rows: threshold 703 -> selected 352

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 397 | 8.0096 | 1.3283 | 0.1131 | 4.3139 |
| Test Selector | 352 | 20.5055 | 2.366 | 0.3239 | 1.7932 |
| Test All Signals | 1115 | 33.681 | 2.0785 | 0.2049 | 2.2311 |

| Retention Metric | Value |
| --- | --- |
| trade_retain_pct | 31.57 |
| pnl_retain_pct | 60.88 |
| pnl_delta | -13.1755 |
| profit_factor_delta | 0.2875 |
