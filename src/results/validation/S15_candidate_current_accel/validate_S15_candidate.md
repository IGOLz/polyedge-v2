# Validation: S15_setup_window_end=30_breakout_scan_start=25_breakout_scan_end=240_breakout_buffer=0.01_confirmation_points=1_feature_window=5_min_underlying_return=0.0005_min_trade_count=40.0_stop_loss=0.35_take_profit=0.75

- Generated at: 2026-03-21T22:44:53.756032+00:00
- Strategy: S15
- Source: S15:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 5407 |
| win_rate_pct | 65.8 |
| total_pnl | 115.459 |
| profit_factor | 1.5689 |
| sharpe_ratio | 0.1595 |
| max_drawdown | 4.139 |
| eligible_markets | 10680 |
| accelerated | True |
| skipped_markets_missing_features | 1440 |

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
| 0.0 | 5407 | 167.7999 | 1.8943 | 0.2319 | 3.346 |
| 0.01 | 5407 | 115.459 | 1.5689 | 0.1595 | 4.139 |
| 0.02 | 5407 | 63.4394 | 1.2861 | 0.0877 | 6.1698 |
| 0.03 | 5407 | 11.9735 | 1.0493 | 0.0165 | 19.2997 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 5407 | 115.459 | 1.5689 | 0.1595 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1780 | 320 | 13.3931 | 3.0962 | 0.3737 | 2026-03-14T00:45:00+00:00 | 2026-03-15T04:30:00+00:00 |
| 2 | 1780 | 775 | 20.6344 | 1.8979 | 0.2191 | 2026-03-15T04:30:00+00:00 | 2026-03-16T08:15:00+00:00 |
| 3 | 1780 | 1316 | 28.2858 | 1.5034 | 0.1506 | 2026-03-16T08:20:00+00:00 | 2026-03-17T12:05:00+00:00 |
| 4 | 1780 | 1024 | 22.8257 | 1.5688 | 0.1633 | 2026-03-17T12:10:00+00:00 | 2026-03-18T15:55:00+00:00 |
| 5 | 1780 | 1090 | 15.239 | 1.3378 | 0.1026 | 2026-03-18T16:00:00+00:00 | 2026-03-19T20:00:00+00:00 |
| 6 | 1780 | 882 | 15.081 | 1.4692 | 0.1306 | 2026-03-19T20:00:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2669 | 993 | 33.1788 | 2.0591 | 0.261 |
| eth | 2669 | 1597 | 26.2101 | 1.3911 | 0.1177 |
| sol | 2670 | 1484 | 33.9716 | 1.6342 | 0.1742 |
| xrp | 2672 | 1333 | 22.0985 | 1.433 | 0.1243 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2672 | 1421 | 16.7647 | 1.1969 | 0.0723 |
| 5m | 8008 | 3986 | 98.6943 | 1.8379 | 0.2037 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 243 | 9.9392 | 2.7929 | 0.3495 |
| 2026-03-15 | 1536 | 486 | 15.9108 | 2.4 | 0.2941 |
| 2026-03-16 | 1536 | 1128 | 25.6179 | 1.5816 | 0.165 |
| 2026-03-17 | 1536 | 1035 | 25.7191 | 1.6181 | 0.1785 |
| 2026-03-18 | 1536 | 854 | 13.9344 | 1.4097 | 0.1202 |
| 2026-03-19 | 1521 | 875 | 12.3223 | 1.3395 | 0.1035 |
| 2026-03-20 | 1527 | 786 | 12.0153 | 1.3997 | 0.1147 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 98.9338 |
| p50_total_pnl | 115.5225 |
| p95_total_pnl | 131.9247 |
| mean_total_pnl | 115.3328 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | higher | 0.0005 | 0.001 | 47.1561 | -68.3029 | 2.3251 | 0.2642 |
| take_profit | lower | 0.75 | 0.7 | 86.7877 | -28.6713 | 1.5974 | 0.1543 |
| breakout_scan_end | lower | 240 | 180 | 88.574 | -26.885 | 1.4722 | 0.1387 |
| setup_window_end | higher | 30 | 45 | 92.2253 | -23.2337 | 1.5298 | 0.144 |
| confirmation_points | higher | 1 | 2 | 93.91 | -21.549 | 1.5346 | 0.1453 |
| feature_window | higher | 5 | 10 | 103.3704 | -12.0886 | 1.3559 | 0.1103 |
| min_trade_count | lower | 40.0 | 20.0 | 105.1304 | -10.3286 | 1.4614 | 0.1353 |
| stop_loss | lower | 0.35 | 0.3 | 107.7291 | -7.7299 | 1.4878 | 0.1372 |
| breakout_scan_start | higher | 25 | 40 | 109.2063 | -6.2527 | 1.5719 | 0.1575 |
| breakout_buffer | higher | 0.01 | 0.015 | 109.5469 | -5.9121 | 1.5661 | 0.1567 |
| take_profit | higher | 0.75 | 0.8 | 118.7216 | 3.2626 | 1.4088 | 0.13 |
| setup_window_end | lower | 30 | 20 | 118.0502 | 2.5912 | 1.5224 | 0.1527 |
