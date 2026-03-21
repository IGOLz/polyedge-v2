# Validation: S13_feature_window=5_entry_window_start=20_entry_window_end=240_min_underlying_return=0.001_min_market_confirmation=0.0_max_market_delta=0.05_max_price_distance_from_mid=0.2_max_underlying_vol=0.006_stop_loss=0.25_take_profit=0.8

- Generated at: 2026-03-21T14:53:42.012615+00:00
- Strategy: S13
- Source: S13:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 258 |
| win_rate_pct | 88.37 |
| total_pnl | 30.9783 |
| profit_factor | 3.9469 |
| sharpe_ratio | 0.6626 |
| max_drawdown | 1.5131 |
| eligible_markets | 10680 |
| accelerated | True |
| skipped_markets_missing_features | 936 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| feature_window | 5 |
| entry_window_start | 20 |
| entry_window_end | 240 |
| min_underlying_return | 0.001 |
| min_market_confirmation | 0.0 |
| max_market_delta | 0.05 |
| max_price_distance_from_mid | 0.2 |
| max_underlying_vol | 0.006 |
| stop_loss | 0.25 |
| take_profit | 0.8 |

## Default Drift

No drift from default/live configuration.

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 258 | 33.5086 | 4.2808 | 0.7168 | 1.4441 |
| 0.01 | 258 | 30.9783 | 3.9469 | 0.6626 | 1.5131 |
| 0.02 | 258 | 28.4518 | 3.6318 | 0.6084 | 1.5822 |
| 0.03 | 258 | 25.9272 | 3.3339 | 0.5543 | 1.6512 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 258 | 30.9783 | 3.9469 | 0.6626 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2670 | 8 | 1.228 | 4.4515 | 0.724 | 2026-03-14T00:45:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 2670 | 147 | 16.0064 | 3.4756 | 0.5909 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:05:00+00:00 |
| 3 | 2670 | 65 | 9.0613 | 5.3728 | 0.8261 | 2026-03-17T12:10:00+00:00 | 2026-03-19T05:50:00+00:00 |
| 4 | 2670 | 38 | 4.6826 | 3.8931 | 0.6592 | 2026-03-19T05:50:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2669 | 52 | 6.8603 | 5.9663 | 0.8419 |
| eth | 2669 | 90 | 10.687 | 3.742 | 0.6337 |
| sol | 2670 | 67 | 7.7502 | 3.4831 | 0.6035 |
| xrp | 2672 | 49 | 5.6808 | 3.6897 | 0.6295 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2672 | 135 | 13.3426 | 2.7038 | 0.4686 |
| 5m | 8008 | 123 | 17.6357 | 7.5777 | 1.0328 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 2 | 0.3781 | 378.141 | 2.0814 |
| 2026-03-15 | 1536 | 28 | 4.5254 | 7.4499 | 1.0462 |
| 2026-03-16 | 1536 | 80 | 7.9858 | 3.0707 | 0.5269 |
| 2026-03-17 | 1536 | 70 | 7.628 | 3.2915 | 0.5585 |
| 2026-03-18 | 1536 | 38 | 5.3227 | 6.2885 | 0.9011 |
| 2026-03-19 | 1521 | 29 | 4.6796 | 8.6541 | 1.125 |
| 2026-03-20 | 1527 | 11 | 0.4586 | 1.4554 | 0.1669 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 25.4933 |
| p50_total_pnl | 31.007 |
| p95_total_pnl | 35.2262 |
| mean_total_pnl | 30.9034 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | lower | 0.001 | 0.0005 | 84.974 | 53.9957 | 1.4119 | 0.1593 |
| min_underlying_return | higher | 0.001 | 0.0015 | 5.9498 | -25.0285 | 3.6313 | 0.6087 |
| max_market_delta | lower | 0.05 | 0.03 | 18.826 | -12.1523 | 5.7789 | 0.8544 |
| feature_window | higher | 5 | 10 | 24.583 | -6.3953 | 2.2251 | 0.3772 |
| max_price_distance_from_mid | lower | 0.2 | 0.16 | 25.2057 | -5.7726 | 3.7407 | 0.6647 |
| entry_window_end | lower | 240 | 180 | 25.5635 | -5.4148 | 3.4974 | 0.5987 |
| min_market_confirmation | higher | 0.0 | 0.003 | 26.148 | -4.8303 | 3.5594 | 0.6075 |
| take_profit | lower | 0.8 | 0.75 | 26.3158 | -4.6625 | 5.066 | 0.7331 |
| max_market_delta | higher | 0.05 | 0.07 | 34.809 | 3.8307 | 2.6063 | 0.4529 |
| entry_window_start | higher | 20 | 30 | 27.649 | -3.3293 | 3.9634 | 0.6589 |
| entry_window_start | lower | 20 | 10 | 28.715 | -2.2633 | 2.8803 | 0.5045 |
| stop_loss | higher | 0.25 | 0.3 | 29.1246 | -1.8537 | 3.6636 | 0.6337 |
| stop_loss | lower | 0.25 | 0.2 | 29.5452 | -1.4331 | 3.4734 | 0.5849 |
| max_underlying_vol | higher | 0.006 | 0.01 | 30.9783 | 0.0 | 3.9469 | 0.6626 |
