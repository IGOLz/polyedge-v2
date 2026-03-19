# Validation: S5_entry_window_start=45_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.02_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:42:48.681844+00:00
- Strategy: S5
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 381 |
| win_rate_pct | 68.24 |
| total_pnl | 13.3738 |
| profit_factor | 1.4862 |
| sharpe_ratio | 0.1925 |
| max_drawdown | 1.9187 |
| eligible_markets | 3399 |
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
| 0.0 | 381 | 17.1575 | 1.6523 | 0.2469 | 1.5807 |
| 0.01 | 381 | 13.3738 | 1.4862 | 0.1925 | 1.9187 |
| 0.02 | 381 | 9.5908 | 1.334 | 0.138 | 2.63 |
| 0.03 | 381 | 5.8124 | 1.1943 | 0.0836 | 3.4831 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 381 | 13.3738 | 1.4862 | 0.1925 | 0 |
| 1 | 381 | 11.1221 | 1.4009 | 0.1604 | 0 |
| 2 | 381 | 11.8777 | 1.4395 | 0.172 | 0 |
| 3 | 381 | 11.278 | 1.4174 | 0.1627 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 567 | 51 | 2.723 | 1.8427 | 0.296 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:20:00+00:00 |
| 2 | 567 | 68 | 2.8474 | 1.5873 | 0.2229 | 2026-03-15T00:20:00+00:00 | 2026-03-15T23:55:00+00:00 |
| 3 | 567 | 57 | 2.7063 | 1.7335 | 0.2669 | 2026-03-16T00:00:00+00:00 | 2026-03-16T23:35:00+00:00 |
| 4 | 566 | 65 | 2.5375 | 1.5365 | 0.2074 | 2026-03-16T23:35:00+00:00 | 2026-03-17T23:10:00+00:00 |
| 5 | 566 | 63 | 0.2286 | 1.0419 | 0.0198 | 2026-03-17T23:10:00+00:00 | 2026-03-18T22:45:00+00:00 |
| 6 | 566 | 77 | 2.3311 | 1.4194 | 0.1689 | 2026-03-18T22:45:00+00:00 | 2026-03-19T22:30:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| eth | 1699 | 199 | 5.7388 | 1.3792 | 0.1559 |
| sol | 1700 | 182 | 7.6349 | 1.6169 | 0.2334 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 3399 | 381 | 13.3738 | 1.4862 | 0.1925 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 558 | 51 | 2.723 | 1.8427 | 0.296 |
| 2026-03-15 | 576 | 68 | 2.8474 | 1.5873 | 0.2229 |
| 2026-03-16 | 576 | 64 | 2.7992 | 1.6368 | 0.2389 |
| 2026-03-17 | 576 | 67 | 3.3791 | 1.8001 | 0.2852 |
| 2026-03-18 | 576 | 71 | -0.5849 | 0.9132 | -0.044 |
| 2026-03-19 | 537 | 60 | 2.21 | 1.5429 | 0.2082 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 99.9 |
| p05_total_pnl | 7.3613 |
| p50_total_pnl | 13.4202 |
| p95_total_pnl | 19.2921 |
| mean_total_pnl | 13.4313 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | -3.4197 | -16.7935 | 0.9209 | -0.0398 |
| take_profit | lower | 0.7 | 0.65 | 8.5352 | -4.8386 | 1.3782 | 0.1465 |
| entry_window_start | higher | 45 | 60 | 8.794 | -4.5798 | 1.3268 | 0.1366 |
| min_cross_move | higher | 0.04 | 0.05 | 10.7745 | -2.5993 | 1.3765 | 0.1549 |
| confirmation_lookback | lower | 5 | 3 | 10.8374 | -2.5364 | 1.3797 | 0.1562 |
| approach_lookback | lower | 12 | 8 | 10.8763 | -2.4975 | 1.3929 | 0.161 |
| confirmation_min_move | higher | 0.01 | 0.015 | 11.4236 | -1.9502 | 1.4104 | 0.1666 |
| price_range_low | higher | 0.45 | 0.47 | 12.2048 | -1.169 | 1.4747 | 0.1887 |
| stop_loss | lower | 0.35 | 0.3 | 12.2727 | -1.1011 | 1.4015 | 0.1599 |
| price_range_high | lower | 0.6 | 0.58 | 12.8196 | -0.5542 | 1.4646 | 0.1858 |
| entry_window_end | higher | 180 | 240 | 13.2629 | -0.1109 | 1.3978 | 0.162 |
| cross_buffer | lower | 0.02 | 0.015 | 13.3738 | 0.0 | 1.4862 | 0.1925 |
