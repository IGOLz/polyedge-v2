# Validation: S14_feature_window=30_entry_window_start=45_entry_window_end=240_min_market_delta_abs=0.06_max_underlying_return_abs=0.0015_extreme_price_low=0.35_extreme_price_high=0.65_require_direction_mismatch=True_stop_loss=0.25_take_profit=0.75

- Generated at: 2026-03-21T16:19:46.969947+00:00
- Strategy: S14
- Source: S14:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 4175 |
| win_rate_pct | 23.28 |
| total_pnl | 64.8045 |
| profit_factor | 1.4346 |
| sharpe_ratio | 0.0973 |
| max_drawdown | 4.8451 |
| eligible_markets | 10661 |
| accelerated | True |
| skipped_markets_missing_features | 1045 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| feature_window | 30 |
| entry_window_start | 45 |
| entry_window_end | 240 |
| min_market_delta_abs | 0.06 |
| max_underlying_return_abs | 0.0015 |
| extreme_price_low | 0.35 |
| extreme_price_high | 0.65 |
| require_direction_mismatch | True |
| stop_loss | 0.25 |
| take_profit | 0.75 |

## Default Drift

No drift from default/live configuration.

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 4175 | 106.9926 | 1.893 | 0.1606 | 2.0062 |
| 0.01 | 4175 | 64.8045 | 1.4346 | 0.0973 | 4.8451 |
| 0.02 | 4175 | 22.6348 | 1.1246 | 0.034 | 9.5101 |
| 0.03 | 4175 | -19.5392 | 0.9095 | -0.0294 | 29.8064 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 4175 | 64.8045 | 1.4346 | 0.0973 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2666 | 1001 | 7.5965 | 1.1913 | 0.0483 | 2026-03-14T00:45:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 2665 | 1177 | 25.4435 | 1.6887 | 0.1367 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:00:00+00:00 |
| 3 | 2665 | 1047 | 6.6934 | 1.1702 | 0.043 | 2026-03-17T12:00:00+00:00 | 2026-03-19T05:40:00+00:00 |
| 4 | 2665 | 950 | 25.0711 | 1.7563 | 0.152 | 2026-03-19T05:45:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2665 | 1375 | 14.7759 | 1.2751 | 0.0689 |
| eth | 2664 | 1019 | 19.0874 | 1.5593 | 0.1165 |
| sol | 2665 | 917 | 12.0709 | 1.3835 | 0.0855 |
| xrp | 2667 | 864 | 18.8703 | 1.6328 | 0.1293 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2672 | 191 | 0.3296 | 1.032 | 0.0102 |
| 5m | 7989 | 3984 | 64.475 | 1.4645 | 0.1018 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1484 | 544 | 9.2222 | 1.4397 | 0.0998 |
| 2026-03-15 | 1536 | 614 | 1.3523 | 1.0567 | 0.0152 |
| 2026-03-16 | 1536 | 685 | 12.7114 | 1.5862 | 0.1208 |
| 2026-03-17 | 1536 | 675 | 12.0258 | 1.517 | 0.1103 |
| 2026-03-18 | 1536 | 573 | 4.2722 | 1.2005 | 0.0501 |
| 2026-03-19 | 1521 | 520 | 6.8112 | 1.3431 | 0.0819 |
| 2026-03-20 | 1512 | 564 | 18.4095 | 2.0108 | 0.1843 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 48.7176 |
| p50_total_pnl | 65.3124 |
| p95_total_pnl | 80.7835 |
| mean_total_pnl | 65.0431 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| require_direction_mismatch | higher | True | False | -234.6538 | -299.4583 | 0.7119 | -0.1274 |
| entry_window_end | lower | 240 | 180 | 39.5382 | -25.2663 | 1.3941 | 0.0942 |
| feature_window | lower | 30 | 10 | 47.6516 | -17.1529 | 1.3268 | 0.0793 |
| extreme_price_high | higher | 0.65 | 0.7 | 49.4434 | -15.3611 | 1.4216 | 0.0875 |
| min_market_delta_abs | lower | 0.06 | 0.05 | 53.2418 | -11.5627 | 1.3015 | 0.0707 |
| stop_loss | higher | 0.25 | 0.3 | 54.2763 | -10.5282 | 1.5701 | 0.1051 |
| extreme_price_low | lower | 0.35 | 0.3 | 58.1203 | -6.6842 | 1.517 | 0.1025 |
| stop_loss | lower | 0.25 | 0.2 | 70.5859 | 5.7814 | 1.3103 | 0.0846 |
| take_profit | lower | 0.75 | 0.7 | 59.6078 | -5.1967 | 1.4098 | 0.0961 |
| entry_window_start | lower | 45 | 30 | 67.5011 | 2.6966 | 1.4259 | 0.0976 |
| max_underlying_return_abs | lower | 0.0015 | 0.0012 | 62.3532 | -2.4513 | 1.4181 | 0.0943 |
