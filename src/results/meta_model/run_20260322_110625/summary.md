# Meta-Model Selector

## Summary

- Dataset rows: 8051
- Dataset markets: 6025
- Experts: S14, S15
- Splits: 2

## Overall Test Metrics

| Metric | Selector | All Signals |
| --- | --- | --- |
| total_bets | 1823 | 2272 |
| win_rate_pct | 51.78 | 46.52 |
| total_pnl | 44.924 | 51.0878 |
| profit_factor | 1.7991 | 1.7182 |
| sharpe_ratio | 0.1764 | 0.1572 |
| max_drawdown | 1.8919 | 2.2311 |

## Split Results

### Split 1

- Train days: 2026-03-14, 2026-03-15, 2026-03-16
- Validation days: 2026-03-17
- Embargo days: 2026-03-18
- Test days: 2026-03-19
- Chosen threshold: -0.008512

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 1439 | 36.963 | 1.7954 | 0.1782 | 1.3384 |
| Test Selector | 1157 | 17.4068 | 1.4362 | 0.1087 | 1.5485 |
| Test All Signals | 1157 | 17.4068 | 1.4362 | 0.1087 | 1.5485 |

### Split 2

- Train days: 2026-03-15, 2026-03-16, 2026-03-17
- Validation days: 2026-03-18
- Embargo days: 2026-03-19
- Test days: 2026-03-20
- Chosen threshold: 0.021921

| Block | Trades | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| Validation | 758 | 14.3775 | 1.5082 | 0.1313 | 2.2258 |
| Test Selector | 666 | 27.5172 | 2.6868 | 0.2942 | 1.8919 |
| Test All Signals | 1115 | 33.681 | 2.0785 | 0.2049 | 2.2311 |
