# Validation: S5_entry_window_start=45_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.02_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:37:33.575157+00:00
- Strategy: S5
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 198 |
| win_rate_pct | 66.67 |
| total_pnl | 5.6366 |
| profit_factor | 1.3725 |
| sharpe_ratio | 0.1536 |
| max_drawdown | 1.3229 |
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
| 0.0 | 198 | 7.603 | 1.5253 | 0.2071 | 1.0941 |
| 0.01 | 198 | 5.6366 | 1.3725 | 0.1536 | 1.3229 |
| 0.02 | 198 | 3.6701 | 1.2324 | 0.1 | 1.5517 |
| 0.03 | 198 | 1.7064 | 1.1037 | 0.0465 | 1.8258 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 198 | 5.6366 | 1.3725 | 0.1536 | 0 |
| 1 | 198 | 4.3561 | 1.2823 | 0.118 | 0 |
| 2 | 198 | 4.6839 | 1.3132 | 0.1281 | 0 |
| 3 | 198 | 4.9439 | 1.3372 | 0.1352 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 283 | 29 | 0.1615 | 1.0625 | 0.0285 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 283 | 34 | 1.7987 | 1.8115 | 0.2879 | 2026-03-15T00:20:00+00:00 | 2026-03-15T23:50:00+00:00 |
| 3 | 283 | 31 | 1.7244 | 1.9137 | 0.3149 | 2026-03-15T23:55:00+00:00 | 2026-03-16T23:25:00+00:00 |
| 4 | 283 | 32 | 0.9064 | 1.3544 | 0.144 | 2026-03-16T23:30:00+00:00 | 2026-03-17T23:00:00+00:00 |
| 5 | 283 | 30 | 0.2614 | 1.102 | 0.0469 | 2026-03-17T23:05:00+00:00 | 2026-03-18T22:35:00+00:00 |
| 6 | 283 | 42 | 0.7841 | 1.2358 | 0.1018 | 2026-03-18T22:40:00+00:00 | 2026-03-19T22:25:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| eth | 1698 | 198 | 5.6366 | 1.3725 | 0.1536 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 1698 | 198 | 5.6366 | 1.3725 | 0.1536 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 279 | 29 | 0.1615 | 1.0625 | 0.0285 |
| 2026-03-15 | 288 | 35 | 1.9906 | 1.898 | 0.3116 |
| 2026-03-16 | 288 | 34 | 1.4196 | 1.6004 | 0.2264 |
| 2026-03-17 | 288 | 33 | 1.4069 | 1.6171 | 0.2294 |
| 2026-03-18 | 288 | 36 | 0.1199 | 1.037 | 0.0176 |
| 2026-03-19 | 267 | 31 | 0.538 | 1.2197 | 0.0948 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 98.7 |
| p05_total_pnl | 1.5305 |
| p50_total_pnl | 5.6837 |
| p95_total_pnl | 9.7419 |
| mean_total_pnl | 5.6429 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | -2.9373 | -8.5739 | 0.8735 | -0.0651 |
| entry_window_start | higher | 45 | 60 | 2.8736 | -2.763 | 1.1897 | 0.084 |
| take_profit | lower | 0.7 | 0.65 | 3.4595 | -2.1771 | 1.2791 | 0.1123 |
| approach_lookback | lower | 12 | 8 | 3.6045 | -2.0321 | 1.226 | 0.0986 |
| min_cross_move | higher | 0.04 | 0.05 | 4.0993 | -1.5373 | 1.2608 | 0.1121 |
| confirmation_min_move | higher | 0.01 | 0.015 | 4.2355 | -1.4011 | 1.2741 | 0.1172 |
| entry_window_end | higher | 180 | 240 | 4.6549 | -0.9817 | 1.2535 | 0.1092 |
| confirmation_lookback | lower | 5 | 3 | 4.7323 | -0.9043 | 1.3051 | 0.129 |
| stop_loss | lower | 0.35 | 0.3 | 6.5317 | 0.8951 | 1.4156 | 0.1653 |
| price_range_high | lower | 0.6 | 0.58 | 5.3324 | -0.3042 | 1.3476 | 0.1449 |
| price_range_low | higher | 0.45 | 0.47 | 5.8785 | 0.2419 | 1.4396 | 0.1769 |
| cross_buffer | lower | 0.02 | 0.015 | 5.6366 | 0.0 | 1.3725 | 0.1536 |
