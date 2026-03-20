# Validation: S8_setup_window_end=45_breakout_scan_start=40_breakout_scan_end=240_breakout_buffer=0.01_min_range_width=0.02_max_range_width=0.1_confirmation_points=1_min_distance_from_mid=0.02_stop_loss=0.3_take_profit=0.7

- Generated at: 2026-03-20T15:34:24.482966+00:00
- Strategy: S8
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 1846 |
| win_rate_pct | 69.61 |
| total_pnl | -13.5432 |
| profit_factor | 0.9122 |
| sharpe_ratio | -0.0388 |
| max_drawdown | 15.173 |
| eligible_markets | 10124 |
| accelerated | False |
| skipped_markets_missing_features | 0 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| setup_window_end | 45 |
| breakout_scan_start | 40 |
| breakout_scan_end | 240 |
| breakout_buffer | 0.01 |
| min_range_width | 0.02 |
| max_range_width | 0.1 |
| confirmation_points | 1 |
| min_distance_from_mid | 0.02 |
| stop_loss | 0.3 |
| take_profit | 0.7 |

## Default Drift

| Field | Kind | Default | Candidate |
| --- | --- | --- | --- |
| breakout_buffer | strategy_param | 0.02 | 0.01 |
| breakout_scan_end | strategy_param | 150 | 240 |
| breakout_scan_start | strategy_param | 50 | 40 |
| confirmation_points | strategy_param | 2 | 1 |
| max_range_width | strategy_param | 0.18 | 0.1 |
| min_distance_from_mid | strategy_param | 0.04 | 0.02 |
| min_range_width | strategy_param | 0.03 | 0.02 |

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 1846 | 4.7099 | 1.0316 | 0.0135 | 8.0571 |
| 0.01 | 1846 | -13.5432 | 0.9122 | -0.0388 | 15.173 |
| 0.02 | 1846 | -31.7741 | 0.8014 | -0.0909 | 31.9721 |
| 0.03 | 1846 | -49.9816 | 0.6985 | -0.143 | 49.9035 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 1846 | -13.5432 | 0.9122 | -0.0388 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1688 | 471 | -1.4877 | 0.9608 | -0.0166 | 2026-03-14T00:45:00+00:00 | 2026-03-15T03:00:00+00:00 |
| 2 | 1688 | 280 | -3.8304 | 0.8409 | -0.0723 | 2026-03-15T03:05:00+00:00 | 2026-03-16T05:25:00+00:00 |
| 3 | 1687 | 274 | -0.7289 | 0.9662 | -0.0145 | 2026-03-16T05:30:00+00:00 | 2026-03-17T07:45:00+00:00 |
| 4 | 1687 | 310 | -3.0809 | 0.8842 | -0.0529 | 2026-03-17T07:45:00+00:00 | 2026-03-18T10:10:00+00:00 |
| 5 | 1687 | 251 | 4.1265 | 1.2477 | 0.0935 | 2026-03-18T10:10:00+00:00 | 2026-03-19T12:30:00+00:00 |
| 6 | 1687 | 260 | -8.5417 | 0.6895 | -0.1602 | 2026-03-19T12:30:00+00:00 | 2026-03-20T15:15:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2530 | 507 | -1.2569 | 0.9687 | -0.0133 |
| eth | 2530 | 452 | -5.8947 | 0.8476 | -0.0696 |
| sol | 2531 | 459 | -4.2409 | 0.8937 | -0.0479 |
| xrp | 2533 | 428 | -2.1507 | 0.9395 | -0.0263 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2532 | 1072 | -14.9449 | 0.8382 | -0.0753 |
| 5m | 7592 | 774 | 1.4017 | 1.0226 | 0.0093 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 435 | 0.1532 | 1.0045 | 0.0018 |
| 2026-03-15 | 1536 | 277 | -5.0968 | 0.7952 | -0.0962 |
| 2026-03-16 | 1536 | 238 | -3.0589 | 0.8473 | -0.0693 |
| 2026-03-17 | 1536 | 270 | -0.2236 | 0.9896 | -0.0045 |
| 2026-03-18 | 1536 | 229 | 2.5966 | 1.1613 | 0.0643 |
| 2026-03-19 | 1521 | 258 | -4.694 | 0.8041 | -0.0932 |
| 2026-03-20 | 971 | 139 | -3.2198 | 0.7649 | -0.1128 |

## Exit Reasons

| ExitReason | Count | PnL | AvgPnL | WinRate% |
| --- | --- | --- | --- | --- |
| resolution | 6 | -0.6511 | -0.108525 | 50.0 |
| sl | 525 | -152.2053 | -0.289915 | 0.0 |
| tp | 1315 | 139.3132 | 0.105942 | 97.49 |

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 3.8 |
| p05_total_pnl | -26.9602 |
| p50_total_pnl | -13.1315 |
| p95_total_pnl | -1.079 |
| mean_total_pnl | -13.1105 |
