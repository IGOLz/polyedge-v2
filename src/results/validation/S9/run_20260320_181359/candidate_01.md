# Validation: S9_compression_window=20_compression_max_std=0.008_compression_max_range=0.03_trigger_scan_start=30_trigger_scan_end=180_breakout_distance=0.03_momentum_lookback=15_efficiency_min=0.55_stop_loss=0.4_take_profit=0.7

- Generated at: 2026-03-20T18:14:31.010661+00:00
- Strategy: S9
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 172 |
| win_rate_pct | 70.35 |
| total_pnl | 5.185 |
| profit_factor | 1.5998 |
| sharpe_ratio | 0.2066 |
| max_drawdown | 0.8555 |
| eligible_markets | 7724 |
| accelerated | False |
| skipped_markets_missing_features | 0 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| compression_window | 20 |
| compression_max_std | 0.008 |
| compression_max_range | 0.03 |
| trigger_scan_start | 30 |
| trigger_scan_end | 180 |
| breakout_distance | 0.03 |
| momentum_lookback | 15 |
| efficiency_min | 0.55 |
| stop_loss | 0.4 |
| take_profit | 0.7 |

## Default Drift

No drift from default/live configuration.

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 172 | 6.8809 | 1.8448 | 0.2743 | 0.6915 |
| 0.01 | 172 | 5.185 | 1.5998 | 0.2066 | 0.8555 |
| 0.02 | 172 | 3.4909 | 1.3816 | 0.1391 | 1.1628 |
| 0.03 | 172 | 1.8005 | 1.1864 | 0.0717 | 1.7669 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 172 | 5.185 | 1.5998 | 0.2066 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1288 | 71 | 3.234 | 2.1471 | 0.3403 | 2026-03-14T00:45:00+00:00 | 2026-03-15T03:30:00+00:00 |
| 2 | 1288 | 25 | 1.1357 | 2.3802 | 0.3779 | 2026-03-15T03:35:00+00:00 | 2026-03-16T06:20:00+00:00 |
| 3 | 1287 | 13 | -0.1557 | 0.8422 | -0.0754 | 2026-03-16T06:25:00+00:00 | 2026-03-17T09:10:00+00:00 |
| 4 | 1287 | 25 | 0.0652 | 1.0356 | 0.0155 | 2026-03-17T09:10:00+00:00 | 2026-03-18T12:00:00+00:00 |
| 5 | 1287 | 14 | 0.0936 | 1.121 | 0.0448 | 2026-03-18T12:00:00+00:00 | 2026-03-19T15:00:00+00:00 |
| 6 | 1287 | 24 | 0.8121 | 1.5765 | 0.1949 | 2026-03-19T15:05:00+00:00 | 2026-03-20T18:00:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 1930 | 64 | 2.8968 | 2.0427 | 0.3175 |
| eth | 1930 | 30 | 0.2051 | 1.1078 | 0.0436 |
| sol | 1931 | 37 | 0.7126 | 1.3415 | 0.131 |
| xrp | 1933 | 41 | 1.3705 | 1.7301 | 0.2318 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 7724 | 172 | 5.185 | 1.5998 | 0.2066 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1116 | 66 | 2.9662 | 2.1549 | 0.3403 |
| 2026-03-15 | 1152 | 30 | 1.4036 | 2.307 | 0.3686 |
| 2026-03-16 | 1152 | 10 | -0.4439 | 0.5499 | -0.2652 |
| 2026-03-17 | 1152 | 24 | 0.6493 | 1.5058 | 0.1819 |
| 2026-03-18 | 1152 | 9 | -0.3137 | 0.5853 | -0.2068 |
| 2026-03-19 | 1141 | 15 | -0.38 | 0.7169 | -0.1395 |
| 2026-03-20 | 859 | 18 | 1.3035 | 3.0568 | 0.4758 |

## Exit Reasons

| ExitReason | Count | PnL | AvgPnL | WinRate% |
| --- | --- | --- | --- | --- |
| resolution | 1 | 0.3857 | 0.385667 | 100.0 |
| sl | 40 | -8.3693 | -0.209232 | 0.0 |
| tp | 131 | 13.1686 | 0.100524 | 91.6 |

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 99.6 |
| p05_total_pnl | 2.2016 |
| p50_total_pnl | 5.1102 |
| p95_total_pnl | 8.1577 |
| mean_total_pnl | 5.1683 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compression_window | higher | 20 | 30 | 1.5525 | -3.6325 | 1.3654 | 0.1392 |
| take_profit | lower | 0.7 | 0.65 | 2.0262 | -3.1588 | 1.303 | 0.103 |
| trigger_scan_start | higher | 30 | 45 | 2.1867 | -2.9983 | 1.2536 | 0.0913 |
| compression_max_range | higher | 0.03 | 0.04 | 3.9533 | -1.2317 | 1.3666 | 0.1364 |
| momentum_lookback | lower | 15 | 10 | 4.2678 | -0.9172 | 1.4502 | 0.165 |
| take_profit | higher | 0.7 | 0.75 | 4.3022 | -0.8828 | 1.3435 | 0.1364 |
| compression_max_std | higher | 0.008 | 0.012 | 4.3626 | -0.8224 | 1.3776 | 0.1401 |
| breakout_distance | higher | 0.03 | 0.04 | 4.5931 | -0.5919 | 1.5523 | 0.1888 |
| breakout_distance | lower | 0.03 | 0.02 | 4.717 | -0.468 | 1.5058 | 0.1821 |
| trigger_scan_end | lower | 180 | 150 | 4.8433 | -0.3417 | 1.5631 | 0.1978 |
| efficiency_min | higher | 0.55 | 0.65 | 4.9166 | -0.2684 | 1.6065 | 0.2043 |
| stop_loss | lower | 0.4 | 0.35 | 4.9297 | -0.2553 | 1.5213 | 0.1805 |
