# Validation: S15_setup_window_end=20_breakout_scan_start=25_breakout_scan_end=240_breakout_buffer=0.01_confirmation_points=1_feature_window=5_min_underlying_return=0.0005_min_trade_count=40.0_stop_loss=0.35_take_profit=0.75

- Generated at: 2026-03-21T22:56:12.282193+00:00
- Strategy: S15
- Source: S15:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 5533 |
| win_rate_pct | 66.33 |
| total_pnl | 118.0502 |
| profit_factor | 1.5224 |
| sharpe_ratio | 0.1527 |
| max_drawdown | 5.0693 |
| eligible_markets | 10680 |
| accelerated | True |
| skipped_markets_missing_features | 1452 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| setup_window_end | 20 |
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
| 0.0 | 5533 | 171.6797 | 1.8161 | 0.2221 | 4.2774 |
| 0.01 | 5533 | 118.0502 | 1.5224 | 0.1527 | 5.0693 |
| 0.02 | 5533 | 64.75 | 1.2644 | 0.0838 | 8.1283 |
| 0.03 | 5533 | 11.9689 | 1.045 | 0.0155 | 20.3743 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 5533 | 118.0502 | 1.5224 | 0.1527 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1780 | 326 | 12.7468 | 2.7192 | 0.3358 | 2026-03-14T00:45:00+00:00 | 2026-03-15T04:30:00+00:00 |
| 2 | 1780 | 798 | 21.5851 | 1.8354 | 0.2125 | 2026-03-15T04:30:00+00:00 | 2026-03-16T08:15:00+00:00 |
| 3 | 1780 | 1344 | 29.3201 | 1.477 | 0.1476 | 2026-03-16T08:20:00+00:00 | 2026-03-17T12:05:00+00:00 |
| 4 | 1780 | 1040 | 23.3764 | 1.5273 | 0.1577 | 2026-03-17T12:10:00+00:00 | 2026-03-18T15:55:00+00:00 |
| 5 | 1780 | 1113 | 15.863 | 1.3066 | 0.0981 | 2026-03-18T16:00:00+00:00 | 2026-03-19T20:00:00+00:00 |
| 6 | 1780 | 912 | 15.1589 | 1.4309 | 0.1235 | 2026-03-19T20:00:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2669 | 1026 | 36.1631 | 2.0311 | 0.2644 |
| eth | 2669 | 1629 | 26.4521 | 1.3568 | 0.1114 |
| sol | 2670 | 1519 | 34.1783 | 1.5619 | 0.1625 |
| xrp | 2672 | 1359 | 21.2568 | 1.38 | 0.1136 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2672 | 1455 | 15.5654 | 1.1681 | 0.0638 |
| 5m | 8008 | 4078 | 102.4848 | 1.7682 | 0.1962 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 248 | 10.3694 | 2.7519 | 0.349 |
| 2026-03-15 | 1536 | 499 | 13.8978 | 1.9476 | 0.2294 |
| 2026-03-16 | 1536 | 1155 | 28.9973 | 1.617 | 0.1773 |
| 2026-03-17 | 1536 | 1054 | 24.0485 | 1.5065 | 0.1562 |
| 2026-03-18 | 1536 | 873 | 18.9712 | 1.5333 | 0.1545 |
| 2026-03-19 | 1521 | 893 | 9.5317 | 1.2233 | 0.0736 |
| 2026-03-20 | 1527 | 811 | 12.2344 | 1.3748 | 0.1102 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 100.5954 |
| p50_total_pnl | 118.2666 |
| p95_total_pnl | 133.7364 |
| mean_total_pnl | 117.9094 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | higher | 0.0005 | 0.001 | 51.0163 | -67.0339 | 2.2508 | 0.2603 |
| take_profit | lower | 0.75 | 0.7 | 88.0359 | -30.0143 | 1.5418 | 0.1461 |
| breakout_scan_end | lower | 240 | 180 | 96.2306 | -21.8196 | 1.4578 | 0.1389 |
| confirmation_points | higher | 1 | 2 | 102.4332 | -15.617 | 1.5176 | 0.1462 |
| stop_loss | lower | 0.35 | 0.3 | 107.0661 | -10.9841 | 1.4322 | 0.1273 |
| feature_window | higher | 5 | 10 | 110.1966 | -7.8536 | 1.3464 | 0.1107 |
| min_trade_count | lower | 40.0 | 20.0 | 110.6134 | -7.4368 | 1.4416 | 0.1338 |
| breakout_scan_start | higher | 25 | 40 | 111.7088 | -6.3414 | 1.553 | 0.1555 |
| take_profit | higher | 0.75 | 0.8 | 122.9146 | 4.8644 | 1.3892 | 0.1277 |
| breakout_buffer | higher | 0.01 | 0.015 | 113.4024 | -4.6478 | 1.5244 | 0.1514 |
| setup_window_end | higher | 20 | 30 | 115.459 | -2.5912 | 1.5689 | 0.1595 |
