# Validation: S5_entry_window_start=45_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.02_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:38:49.851625+00:00
- Strategy: S5
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 182 |
| win_rate_pct | 69.78 |
| total_pnl | 7.6349 |
| profit_factor | 1.6169 |
| sharpe_ratio | 0.2334 |
| max_drawdown | 1.1815 |
| eligible_markets | 1699 |
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
| 0.0 | 182 | 9.4424 | 1.7983 | 0.2887 | 0.9546 |
| 0.01 | 182 | 7.6349 | 1.6169 | 0.2334 | 1.1815 |
| 0.02 | 182 | 5.8283 | 1.451 | 0.1782 | 1.5487 |
| 0.03 | 182 | 4.0234 | 1.2987 | 0.123 | 1.9155 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 182 | 7.6349 | 1.6169 | 0.2334 | 0 |
| 1 | 182 | 6.6736 | 1.5418 | 0.2066 | 0 |
| 2 | 182 | 7.1013 | 1.5882 | 0.2192 | 0 |
| 3 | 182 | 6.2417 | 1.5051 | 0.1908 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 284 | 22 | 2.5614 | 4.96 | 0.8368 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:20:00+00:00 |
| 2 | 283 | 33 | 0.8568 | 1.3255 | 0.1332 | 2026-03-15T00:25:00+00:00 | 2026-03-15T23:55:00+00:00 |
| 3 | 283 | 27 | 1.1737 | 1.6513 | 0.2398 | 2026-03-16T00:00:00+00:00 | 2026-03-16T23:30:00+00:00 |
| 4 | 283 | 33 | 1.6311 | 1.7509 | 0.2714 | 2026-03-16T23:35:00+00:00 | 2026-03-17T23:05:00+00:00 |
| 5 | 283 | 32 | 0.235 | 1.0896 | 0.041 | 2026-03-17T23:10:00+00:00 | 2026-03-18T22:40:00+00:00 |
| 6 | 283 | 35 | 1.1769 | 1.4707 | 0.1836 | 2026-03-18T22:45:00+00:00 | 2026-03-19T22:25:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| sol | 1699 | 182 | 7.6349 | 1.6169 | 0.2334 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 1699 | 182 | 7.6349 | 1.6169 | 0.2334 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 279 | 22 | 2.5614 | 4.96 | 0.8368 |
| 2026-03-15 | 288 | 33 | 0.8568 | 1.3255 | 0.1332 |
| 2026-03-16 | 288 | 30 | 1.3797 | 1.6793 | 0.2489 |
| 2026-03-17 | 288 | 34 | 1.9722 | 2.0149 | 0.3411 |
| 2026-03-18 | 288 | 35 | -0.7048 | 0.7987 | -0.1079 |
| 2026-03-19 | 268 | 28 | 1.5697 | 1.9681 | 0.3226 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 3.5434 |
| p50_total_pnl | 7.7405 |
| p95_total_pnl | 11.662 |
| mean_total_pnl | 7.6244 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | -0.4824 | -8.1173 | 0.9759 | -0.0118 |
| take_profit | lower | 0.7 | 0.65 | 5.0335 | -2.6014 | 1.4949 | 0.1837 |
| stop_loss | lower | 0.35 | 0.3 | 5.6387 | -1.9962 | 1.3798 | 0.1515 |
| entry_window_start | higher | 45 | 60 | 5.8182 | -1.8167 | 1.4947 | 0.1938 |
| confirmation_lookback | lower | 5 | 3 | 6.0029 | -1.632 | 1.4606 | 0.1839 |
| price_range_low | higher | 0.45 | 0.47 | 6.2241 | -1.4108 | 1.5045 | 0.198 |
| min_cross_move | higher | 0.04 | 0.05 | 6.5729 | -1.062 | 1.5098 | 0.1996 |
| entry_window_end | higher | 180 | 240 | 8.5058 | 0.8709 | 1.5679 | 0.2175 |
| confirmation_min_move | higher | 0.01 | 0.015 | 7.0859 | -0.549 | 1.5722 | 0.2192 |
| approach_lookback | lower | 12 | 8 | 7.1695 | -0.4654 | 1.6114 | 0.2323 |
| price_range_high | lower | 0.6 | 0.58 | 7.3849 | -0.25 | 1.6026 | 0.2298 |
| cross_buffer | lower | 0.02 | 0.015 | 7.6349 | 0.0 | 1.6169 | 0.2334 |
