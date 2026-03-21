# Validation: S15_setup_window_end=30_breakout_scan_start=25_breakout_scan_end=240_breakout_buffer=0.01_confirmation_points=1_feature_window=5_min_underlying_return=0.0005_min_trade_count=40.0_stop_loss=0.35_take_profit=0.75

- Generated at: 2026-03-21T22:59:00.365842+00:00
- Strategy: S15
- Source: S15:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 3986 |
| win_rate_pct | 65.2 |
| total_pnl | 98.6943 |
| profit_factor | 1.8379 |
| sharpe_ratio | 0.2037 |
| max_drawdown | 2.7285 |
| eligible_markets | 8008 |
| accelerated | True |
| skipped_markets_missing_features | 1092 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| setup_window_end | 30 |
| breakout_scan_start | 25 |
| breakout_scan_end | 240 |
| breakout_buffer | 0.01 |
| confirmation_points | 1 |
| feature_window | 5 |
| min_underlying_return | 0.0005 |
| min_trade_count | 40.0 |
| stop_loss | 0.35 |
| take_profit | 0.75 |

## Default Drift

No drift from default/live configuration.

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 3986 | 137.1118 | 2.2846 | 0.283 | 2.4744 |
| 0.01 | 3986 | 98.6943 | 1.8379 | 0.2037 | 2.7285 |
| 0.02 | 3986 | 60.5861 | 1.4594 | 0.1251 | 4.6763 |
| 0.03 | 3986 | 23.0155 | 1.1555 | 0.0475 | 8.8831 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 3986 | 98.6943 | 1.8379 | 0.2037 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1335 | 225 | 9.8772 | 3.3499 | 0.3921 | 2026-03-14T00:45:00+00:00 | 2026-03-15T04:30:00+00:00 |
| 2 | 1335 | 559 | 13.0549 | 1.852 | 0.2013 | 2026-03-15T04:30:00+00:00 | 2026-03-16T08:20:00+00:00 |
| 3 | 1335 | 983 | 26.7781 | 1.8331 | 0.2109 | 2026-03-16T08:20:00+00:00 | 2026-03-17T12:10:00+00:00 |
| 4 | 1335 | 768 | 17.0766 | 1.6718 | 0.1756 | 2026-03-17T12:10:00+00:00 | 2026-03-18T15:55:00+00:00 |
| 5 | 1334 | 809 | 14.1732 | 1.5381 | 0.1426 | 2026-03-18T16:00:00+00:00 | 2026-03-19T20:00:00+00:00 |
| 6 | 1334 | 642 | 17.7342 | 2.2343 | 0.2545 | 2026-03-19T20:00:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2001 | 721 | 27.1857 | 2.6937 | 0.3377 |
| eth | 2001 | 1174 | 20.8373 | 1.509 | 0.1383 |
| sol | 2002 | 1108 | 30.6307 | 1.9842 | 0.2299 |
| xrp | 2004 | 983 | 20.0405 | 1.6753 | 0.1685 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 8008 | 3986 | 98.6943 | 1.8379 | 0.2037 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1116 | 173 | 7.4068 | 2.8529 | 0.3554 |
| 2026-03-15 | 1152 | 344 | 10.7286 | 2.6098 | 0.304 |
| 2026-03-16 | 1152 | 834 | 20.1336 | 1.7314 | 0.1876 |
| 2026-03-17 | 1152 | 782 | 24.4245 | 2.0636 | 0.2536 |
| 2026-03-18 | 1152 | 636 | 9.3451 | 1.4108 | 0.1138 |
| 2026-03-19 | 1141 | 646 | 11.2342 | 1.5457 | 0.1435 |
| 2026-03-20 | 1143 | 571 | 15.4214 | 2.1592 | 0.2458 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 85.8699 |
| p50_total_pnl | 99.0535 |
| p95_total_pnl | 111.8135 |
| mean_total_pnl | 98.9893 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | higher | 0.0005 | 0.001 | 38.3771 | -60.3172 | 3.1925 | 0.3436 |
| take_profit | lower | 0.75 | 0.7 | 74.8594 | -23.8349 | 1.8509 | 0.1948 |
| breakout_scan_end | lower | 240 | 180 | 77.699 | -20.9953 | 1.689 | 0.1785 |
| setup_window_end | higher | 30 | 45 | 80.5534 | -18.1409 | 1.8194 | 0.1912 |
| confirmation_points | higher | 1 | 2 | 81.9949 | -16.6994 | 1.8431 | 0.1943 |
| take_profit | higher | 0.75 | 0.8 | 111.1098 | 12.4155 | 1.6608 | 0.1811 |
| min_trade_count | lower | 40.0 | 20.0 | 90.0771 | -8.6172 | 1.6643 | 0.1715 |
| feature_window | higher | 5 | 10 | 92.1764 | -6.5179 | 1.5241 | 0.1446 |
| stop_loss | lower | 0.35 | 0.3 | 94.8404 | -3.8539 | 1.745 | 0.1818 |
| setup_window_end | lower | 30 | 20 | 102.4848 | 3.7905 | 1.7682 | 0.1962 |
| breakout_buffer | higher | 0.01 | 0.015 | 94.9762 | -3.7181 | 1.8447 | 0.202 |
| breakout_scan_start | higher | 25 | 40 | 95.3896 | -3.3047 | 1.8804 | 0.2075 |
