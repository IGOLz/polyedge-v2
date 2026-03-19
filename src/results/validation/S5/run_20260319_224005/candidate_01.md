# Validation: S5_entry_window_start=45_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.02_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:40:06.257770+00:00
- Strategy: S5
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 193 |
| win_rate_pct | 64.77 |
| total_pnl | 3.9945 |
| profit_factor | 1.2575 |
| sharpe_ratio | 0.1101 |
| max_drawdown | 1.4153 |
| eligible_markets | 1698 |
| accelerated | True |
| skipped_markets_missing_features | 0 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| entry_window_start | 45 |
| entry_window_end | 180 |
| allowed_hours | [18, 19, 20, 21, 22, 23] |
| price_range_low | 0.45 |
| price_range_high | 0.6 |
| approach_lookback | 12 |
| cross_buffer | 0.02 |
| confirmation_lookback | 5 |
| confirmation_min_move | 0.01 |
| min_cross_move | 0.04 |
| stop_loss | 0.35 |
| take_profit | 0.7 |

## Default Drift

| Field | Kind | Default | Candidate |
| --- | --- | --- | --- |
| approach_lookback | strategy_param | 8 | 12 |
| confirmation_lookback | strategy_param | 4 | 5 |
| confirmation_min_move | strategy_param | 0.015 | 0.01 |
| min_cross_move | strategy_param | 0.05 | 0.04 |

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 193 | 5.9106 | 1.3985 | 0.163 | 1.3158 |
| 0.01 | 193 | 3.9945 | 1.2575 | 0.1101 | 1.4153 |
| 0.02 | 193 | 2.0787 | 1.1284 | 0.0573 | 1.7021 |
| 0.03 | 193 | 0.1644 | 1.0097 | 0.0045 | 1.9901 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 193 | 3.9945 | 1.2575 | 0.1101 | 0 |
| 1 | 193 | 3.4643 | 1.2263 | 0.096 | 0 |
| 2 | 193 | 3.2636 | 1.2147 | 0.091 | 0 |
| 3 | 193 | 3.0288 | 1.201 | 0.0844 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 283 | 28 | 0.0676 | 1.0244 | 0.0112 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 283 | 33 | 0.1611 | 1.0529 | 0.0247 | 2026-03-15T00:20:00+00:00 | 2026-03-15T23:50:00+00:00 |
| 3 | 283 | 27 | 1.105 | 1.6099 | 0.2256 | 2026-03-15T23:55:00+00:00 | 2026-03-16T23:25:00+00:00 |
| 4 | 283 | 37 | 2.56 | 2.4929 | 0.4521 | 2026-03-16T23:30:00+00:00 | 2026-03-17T23:00:00+00:00 |
| 5 | 283 | 34 | 0.7476 | 1.2713 | 0.1146 | 2026-03-17T23:05:00+00:00 | 2026-03-18T22:35:00+00:00 |
| 6 | 283 | 34 | -0.6468 | 0.8104 | -0.1001 | 2026-03-18T22:40:00+00:00 | 2026-03-19T22:25:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| xrp | 1698 | 193 | 3.9945 | 1.2575 | 0.1101 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 1698 | 193 | 3.9945 | 1.2575 | 0.1101 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 279 | 28 | 0.0676 | 1.0244 | 0.0112 |
| 2026-03-15 | 288 | 34 | 0.3028 | 1.0994 | 0.0453 |
| 2026-03-16 | 288 | 31 | 1.3715 | 1.6722 | 0.2455 |
| 2026-03-17 | 288 | 37 | 2.1001 | 2.086 | 0.3582 |
| 2026-03-18 | 288 | 37 | 0.561 | 1.1757 | 0.0777 |
| 2026-03-19 | 267 | 26 | -0.4084 | 0.8383 | -0.0831 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 92.9 |
| p05_total_pnl | -0.435 |
| p50_total_pnl | 4.166 |
| p95_total_pnl | 7.995 |
| mean_total_pnl | 3.9936 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| entry_window_start | higher | 45 | 60 | 1.6664 | -2.3281 | 1.1115 | 0.0506 |
| take_profit | lower | 0.7 | 0.65 | 2.1923 | -1.8022 | 1.1737 | 0.0717 |
| entry_window_end | higher | 180 | 240 | 5.3602 | 1.3657 | 1.3077 | 0.1289 |
| confirmation_lookback | lower | 5 | 3 | 2.8348 | -1.1597 | 1.1775 | 0.0786 |
| price_range_low | higher | 0.45 | 0.47 | 2.851 | -1.1435 | 1.1896 | 0.0836 |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | 3.0895 | -0.905 | 1.174 | 0.0774 |
| stop_loss | lower | 0.35 | 0.3 | 4.6031 | 0.6086 | 1.2805 | 0.1167 |
| price_range_high | lower | 0.6 | 0.58 | 3.4311 | -0.5634 | 1.2165 | 0.0946 |
| confirmation_min_move | higher | 0.01 | 0.015 | 4.4458 | 0.4513 | 1.3008 | 0.1264 |
| approach_lookback | lower | 12 | 8 | 3.5684 | -0.4261 | 1.2328 | 0.1004 |
| min_cross_move | higher | 0.04 | 0.05 | 4.3237 | 0.3292 | 1.2854 | 0.1206 |
| cross_buffer | lower | 0.02 | 0.015 | 3.9945 | 0.0 | 1.2575 | 0.1101 |
