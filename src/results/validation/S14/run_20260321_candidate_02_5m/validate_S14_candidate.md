# Validation: S14_feature_window=30_entry_window_start=45_entry_window_end=240_min_market_delta_abs=0.06_max_underlying_return_abs=0.0015_extreme_price_low=0.35_extreme_price_high=0.65_require_direction_mismatch=True_stop_loss=0.25_take_profit=0.75

- Generated at: 2026-03-21T16:25:31.102268+00:00
- Strategy: S14
- Source: S14:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 3984 |
| win_rate_pct | 23.49 |
| total_pnl | 64.475 |
| profit_factor | 1.4645 |
| sharpe_ratio | 0.1018 |
| max_drawdown | 4.3446 |
| eligible_markets | 7989 |
| accelerated | True |
| skipped_markets_missing_features | 792 |

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
| 0.0 | 3984 | 104.7297 | 1.9436 | 0.1653 | 1.9314 |
| 0.01 | 3984 | 64.475 | 1.4645 | 0.1018 | 4.3446 |
| 0.02 | 3984 | 24.2371 | 1.1427 | 0.0383 | 8.6378 |
| 0.03 | 3984 | -16.004 | 0.9209 | -0.0253 | 26.7878 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 3984 | 64.475 | 1.4645 | 0.1018 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1998 | 961 | 9.3943 | 1.2533 | 0.0617 | 2026-03-14T00:50:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 1997 | 1116 | 23.8019 | 1.6943 | 0.136 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:00:00+00:00 |
| 3 | 1997 | 999 | 5.9228 | 1.16 | 0.0403 | 2026-03-17T12:00:00+00:00 | 2026-03-19T05:35:00+00:00 |
| 4 | 1997 | 908 | 25.356 | 1.8335 | 0.1612 | 2026-03-19T05:40:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 1997 | 1314 | 12.5712 | 1.2459 | 0.0621 |
| eth | 1996 | 967 | 20.5219 | 1.6621 | 0.1312 |
| sol | 1997 | 878 | 12.1185 | 1.417 | 0.0903 |
| xrp | 1999 | 825 | 19.2634 | 1.697 | 0.1379 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 7989 | 3984 | 64.475 | 1.4645 | 0.1018 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1112 | 527 | 9.4593 | 1.4758 | 0.1056 |
| 2026-03-15 | 1152 | 579 | 1.574 | 1.0716 | 0.0189 |
| 2026-03-16 | 1152 | 656 | 12.9604 | 1.6438 | 0.1286 |
| 2026-03-17 | 1152 | 642 | 11.9551 | 1.5523 | 0.1151 |
| 2026-03-18 | 1152 | 544 | 3.3037 | 1.1654 | 0.0416 |
| 2026-03-19 | 1141 | 502 | 6.9359 | 1.3744 | 0.087 |
| 2026-03-20 | 1128 | 534 | 18.2866 | 2.0962 | 0.1932 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 50.3653 |
| p50_total_pnl | 64.1973 |
| p95_total_pnl | 81.2107 |
| mean_total_pnl | 64.9004 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| require_direction_mismatch | higher | True | False | -188.2358 | -252.7108 | 0.6923 | -0.135 |
| entry_window_end | lower | 240 | 180 | 39.0777 | -25.3973 | 1.4209 | 0.0986 |
| feature_window | lower | 30 | 10 | 48.3455 | -16.1295 | 1.359 | 0.0854 |
| extreme_price_high | higher | 0.65 | 0.7 | 49.2817 | -15.1933 | 1.45 | 0.0914 |
| min_market_delta_abs | lower | 0.06 | 0.05 | 52.7452 | -11.7298 | 1.3238 | 0.0744 |
| stop_loss | higher | 0.25 | 0.3 | 54.4936 | -9.9814 | 1.613 | 0.1105 |
| extreme_price_low | lower | 0.35 | 0.3 | 56.3198 | -8.1552 | 1.5258 | 0.1032 |
| stop_loss | lower | 0.25 | 0.2 | 70.5571 | 6.0821 | 1.333 | 0.0891 |
| take_profit | lower | 0.75 | 0.7 | 59.0023 | -5.4727 | 1.4359 | 0.1001 |
| max_underlying_return_abs | lower | 0.0015 | 0.0012 | 61.9223 | -2.5527 | 1.4457 | 0.0985 |
| entry_window_start | lower | 45 | 30 | 66.6009 | 2.1259 | 1.4512 | 0.1014 |
