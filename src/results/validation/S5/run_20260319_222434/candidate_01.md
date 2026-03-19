# Validation: S5_entry_window_start=45_entry_window_end=240_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.015_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:24:35.314558+00:00
- Strategy: S5
- Source: results\optimization\S5\run_20260319_204940\Test_optimize_S5_Results.csv

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 655 |
| win_rate_pct | 66.41 |
| total_pnl | 18.2643 |
| profit_factor | 1.3612 |
| sharpe_ratio | 0.149 |
| max_drawdown | 2.9185 |
| eligible_markets | 5086 |
| accelerated | True |
| skipped_markets_missing_features | 0 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| entry_window_start | 45 |
| entry_window_end | 240 |
| allowed_hours | [18, 19, 20, 21, 22, 23] |
| price_range_low | 0.45 |
| price_range_high | 0.6 |
| approach_lookback | 12 |
| cross_buffer | 0.015 |
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
| cross_buffer | strategy_param | 0.02 | 0.015 |
| entry_window_end | strategy_param | 180 | 240 |
| min_cross_move | strategy_param | 0.05 | 0.04 |

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 655 | 24.7683 | 1.5121 | 0.2021 | 2.1831 |
| 0.01 | 655 | 18.2643 | 1.3612 | 0.149 | 2.9185 |
| 0.02 | 655 | 11.7618 | 1.223 | 0.0959 | 3.6541 |
| 0.03 | 655 | 5.2659 | 1.0958 | 0.0429 | 4.4872 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 655 | 18.2643 | 1.3612 | 0.149 | 0 |
| 1 | 655 | 14.4702 | 1.2872 | 0.1191 | 0 |
| 2 | 655 | 14.6876 | 1.2966 | 0.1216 | 0 |
| 3 | 655 | 13.6157 | 1.2765 | 0.1125 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 848 | 95 | 3.3646 | 1.4557 | 0.1787 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 848 | 109 | 2.1325 | 1.2326 | 0.1008 | 2026-03-15T00:15:00+00:00 | 2026-03-15T23:50:00+00:00 |
| 3 | 848 | 102 | 5.0585 | 1.7789 | 0.2793 | 2026-03-15T23:50:00+00:00 | 2026-03-16T23:20:00+00:00 |
| 4 | 848 | 109 | 4.1716 | 1.5427 | 0.2094 | 2026-03-16T23:25:00+00:00 | 2026-03-17T22:55:00+00:00 |
| 5 | 847 | 110 | 3.2794 | 1.4019 | 0.1642 | 2026-03-17T22:55:00+00:00 | 2026-03-18T22:25:00+00:00 |
| 6 | 847 | 130 | 0.2578 | 1.0221 | 0.0105 | 2026-03-18T22:30:00+00:00 | 2026-03-19T22:10:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| eth | 1695 | 222 | 4.6723 | 1.2573 | 0.1106 |
| sol | 1696 | 212 | 8.3437 | 1.5571 | 0.2141 |
| xrp | 1695 | 221 | 5.2483 | 1.3013 | 0.1266 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 5086 | 655 | 18.2643 | 1.3612 | 0.149 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 837 | 95 | 3.3646 | 1.4557 | 0.1787 |
| 2026-03-15 | 864 | 111 | 2.4659 | 1.269 | 0.1149 |
| 2026-03-16 | 864 | 115 | 5.3397 | 1.6999 | 0.2574 |
| 2026-03-17 | 864 | 116 | 5.2947 | 1.711 | 0.26 |
| 2026-03-18 | 864 | 119 | 0.7471 | 1.0702 | 0.0329 |
| 2026-03-19 | 793 | 99 | 1.0523 | 1.127 | 0.0572 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 10.7702 |
| p50_total_pnl | 18.6949 |
| p95_total_pnl | 26.1947 |
| mean_total_pnl | 18.6126 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | 1.3111 | -16.9532 | 1.019 | 0.0091 |
| entry_window_start | higher | 45 | 60 | 10.4668 | -7.7975 | 1.2057 | 0.09 |
| take_profit | lower | 0.7 | 0.65 | 10.6286 | -7.6357 | 1.2566 | 0.1037 |
| approach_lookback | lower | 12 | 8 | 14.6192 | -3.6451 | 1.284 | 0.1207 |
| confirmation_lookback | lower | 5 | 3 | 14.8797 | -3.3846 | 1.2852 | 0.1212 |
| price_range_low | higher | 0.45 | 0.47 | 15.7001 | -2.5642 | 1.3247 | 0.1359 |
| min_cross_move | higher | 0.04 | 0.05 | 16.086 | -2.1783 | 1.3133 | 0.1315 |
| stop_loss | lower | 0.35 | 0.3 | 16.2691 | -1.9952 | 1.2904 | 0.1205 |
| confirmation_min_move | higher | 0.01 | 0.015 | 16.6393 | -1.625 | 1.3298 | 0.1375 |
| entry_window_end | lower | 240 | 180 | 17.1214 | -1.1429 | 1.3998 | 0.1629 |
| price_range_high | lower | 0.6 | 0.58 | 17.718 | -0.5463 | 1.3518 | 0.1462 |
| cross_buffer | higher | 0.015 | 0.02 | 18.2643 | 0.0 | 1.3612 | 0.149 |
