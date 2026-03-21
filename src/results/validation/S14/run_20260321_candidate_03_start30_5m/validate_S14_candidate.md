# Validation: S14_feature_window=30_entry_window_start=30_entry_window_end=240_min_market_delta_abs=0.06_max_underlying_return_abs=0.0015_extreme_price_low=0.35_extreme_price_high=0.65_require_direction_mismatch=True_stop_loss=0.25_take_profit=0.75

- Generated at: 2026-03-21T16:30:30.321017+00:00
- Strategy: S14
- Source: S14:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 4065 |
| win_rate_pct | 23.57 |
| total_pnl | 66.6009 |
| profit_factor | 1.4512 |
| sharpe_ratio | 0.1014 |
| max_drawdown | 4.9104 |
| eligible_markets | 7989 |
| accelerated | True |
| skipped_markets_missing_features | 799 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| feature_window | 30 |
| entry_window_start | 30 |
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
| 0.0 | 4065 | 107.682 | 1.9042 | 0.1639 | 2.4512 |
| 0.01 | 4065 | 66.6009 | 1.4512 | 0.1014 | 4.9104 |
| 0.02 | 4065 | 25.5415 | 1.1425 | 0.0389 | 10.7931 |
| 0.03 | 4065 | -15.523 | 0.9269 | -0.0236 | 27.3748 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 4065 | 66.6009 | 1.4512 | 0.1014 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1998 | 983 | 10.9081 | 1.2798 | 0.0685 | 2026-03-14T00:50:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 1997 | 1141 | 24.5227 | 1.6593 | 0.1341 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:00:00+00:00 |
| 3 | 1997 | 1016 | 6.6874 | 1.1712 | 0.0437 | 2026-03-17T12:00:00+00:00 | 2026-03-19T05:35:00+00:00 |
| 4 | 1997 | 925 | 24.4825 | 1.7567 | 0.1525 | 2026-03-19T05:40:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 1997 | 1342 | 14.4512 | 1.266 | 0.068 |
| eth | 1996 | 984 | 20.7711 | 1.6287 | 0.1287 |
| sol | 1997 | 896 | 11.1934 | 1.3597 | 0.0812 |
| xrp | 1999 | 843 | 20.1852 | 1.6935 | 0.1396 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 7989 | 4065 | 66.6009 | 1.4512 | 0.1014 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1112 | 540 | 11.5858 | 1.5637 | 0.1233 |
| 2026-03-15 | 1152 | 592 | 0.5285 | 1.0224 | 0.0061 |
| 2026-03-16 | 1152 | 667 | 14.0251 | 1.6511 | 0.1329 |
| 2026-03-17 | 1152 | 657 | 12.5384 | 1.5334 | 0.1153 |
| 2026-03-18 | 1152 | 554 | 3.7951 | 1.1806 | 0.0459 |
| 2026-03-19 | 1141 | 511 | 5.9956 | 1.3086 | 0.0743 |
| 2026-03-20 | 1128 | 544 | 18.1325 | 2.011 | 0.1867 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 52.4402 |
| p50_total_pnl | 67.6412 |
| p95_total_pnl | 84.566 |
| mean_total_pnl | 67.8518 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| require_direction_mismatch | higher | True | False | -165.2711 | -231.872 | 0.7487 | -0.1105 |
| entry_window_end | lower | 240 | 180 | 41.1169 | -25.484 | 1.3981 | 0.0967 |
| extreme_price_high | higher | 0.65 | 0.7 | 48.2165 | -18.3844 | 1.4151 | 0.0871 |
| feature_window | lower | 30 | 10 | 48.9864 | -17.6145 | 1.3397 | 0.0829 |
| min_market_delta_abs | lower | 0.06 | 0.05 | 55.4935 | -11.1074 | 1.3223 | 0.0756 |
| extreme_price_low | lower | 0.35 | 0.3 | 57.9894 | -8.6115 | 1.518 | 0.1034 |
| stop_loss | higher | 0.25 | 0.3 | 58.5694 | -8.0315 | 1.6221 | 0.1138 |
| stop_loss | lower | 0.25 | 0.2 | 74.0884 | 7.4875 | 1.3321 | 0.0904 |
| take_profit | lower | 0.75 | 0.7 | 61.6803 | -4.9206 | 1.4289 | 0.1007 |
| max_underlying_return_abs | lower | 0.0015 | 0.0012 | 63.5479 | -3.053 | 1.4301 | 0.0975 |
| entry_window_start | higher | 30 | 45 | 64.475 | -2.1259 | 1.4645 | 0.1018 |
| entry_window_start | lower | 30 | 20 | 66.6009 | 0.0 | 1.4512 | 0.1014 |
