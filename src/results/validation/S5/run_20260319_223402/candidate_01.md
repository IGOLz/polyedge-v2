# Validation: S5_entry_window_start=45_entry_window_end=180_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.02_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:34:02.524148+00:00
- Strategy: S5
- Source: manual-json

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 573 |
| win_rate_pct | 67.02 |
| total_pnl | 17.266 |
| profit_factor | 1.4013 |
| sharpe_ratio | 0.1634 |
| max_drawdown | 2.765 |
| eligible_markets | 5092 |
| accelerated | True |
| skipped_markets_missing_features | 0 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| entry_window_start | 45 |
| entry_window_end | 180 |
| allowed_hours | [18, 19, 20, 21, 22, 23] |
| price_range_low | 0.45 |
| price_range_high | 0.6 |
| approach_lookback | 12 |
| cross_buffer | 0.02 |
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
| min_cross_move | strategy_param | 0.05 | 0.04 |

## Slippage Sweep

| Slippage | Bets | PnL | PF | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 573 | 22.9561 | 1.558 | 0.2173 | 2.3574 |
| 0.01 | 573 | 17.266 | 1.4013 | 0.1634 | 2.765 |
| 0.02 | 573 | 11.577 | 1.2578 | 0.1096 | 3.1728 |
| 0.03 | 573 | 5.8942 | 1.126 | 0.0558 | 4.0404 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 573 | 17.266 | 1.4013 | 0.1634 | 0 |
| 1 | 573 | 14.4939 | 1.3366 | 0.1377 | 0 |
| 2 | 573 | 15.0488 | 1.3563 | 0.1436 | 0 |
| 3 | 573 | 14.2144 | 1.3377 | 0.1353 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 849 | 79 | 2.7906 | 1.465 | 0.1823 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 849 | 100 | 2.8166 | 1.3568 | 0.1472 | 2026-03-15T00:20:00+00:00 | 2026-03-15T23:50:00+00:00 |
| 3 | 849 | 84 | 3.8515 | 1.7001 | 0.2571 | 2026-03-15T23:55:00+00:00 | 2026-03-16T23:25:00+00:00 |
| 4 | 849 | 102 | 5.0975 | 1.791 | 0.2838 | 2026-03-16T23:30:00+00:00 | 2026-03-17T23:00:00+00:00 |
| 5 | 848 | 96 | 1.6624 | 1.2166 | 0.095 | 2026-03-17T23:05:00+00:00 | 2026-03-18T22:35:00+00:00 |
| 6 | 848 | 112 | 1.0474 | 1.1102 | 0.0503 | 2026-03-18T22:35:00+00:00 | 2026-03-19T22:20:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| eth | 1697 | 198 | 5.6366 | 1.3725 | 0.1536 |
| sol | 1698 | 182 | 7.6349 | 1.6169 | 0.2334 |
| xrp | 1697 | 193 | 3.9945 | 1.2575 | 0.1101 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 5092 | 573 | 17.266 | 1.4013 | 0.1634 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 837 | 79 | 2.7906 | 1.465 | 0.1823 |
| 2026-03-15 | 864 | 102 | 3.1501 | 1.399 | 0.1622 |
| 2026-03-16 | 864 | 95 | 4.1707 | 1.648 | 0.2423 |
| 2026-03-17 | 864 | 104 | 5.4792 | 1.8899 | 0.3104 |
| 2026-03-18 | 864 | 108 | -0.0239 | 0.9976 | -0.0012 |
| 2026-03-19 | 799 | 85 | 1.6993 | 1.2576 | 0.1098 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 10.4453 |
| p50_total_pnl | 17.2549 |
| p95_total_pnl | 24.2359 |
| mean_total_pnl | 17.3076 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | -0.3302 | -17.5962 | 0.9946 | -0.0026 |
| entry_window_start | higher | 45 | 60 | 10.3582 | -6.9078 | 1.2475 | 0.1066 |
| take_profit | lower | 0.7 | 0.65 | 10.6853 | -6.5807 | 1.3037 | 0.1204 |
| confirmation_lookback | lower | 5 | 3 | 13.5699 | -3.6961 | 1.3049 | 0.1289 |
| approach_lookback | lower | 12 | 8 | 14.1993 | -3.0667 | 1.3301 | 0.1381 |
| price_range_low | higher | 0.45 | 0.47 | 14.9536 | -2.3124 | 1.367 | 0.1515 |
| min_cross_move | higher | 0.04 | 0.05 | 14.9959 | -2.2701 | 1.3426 | 0.1425 |
| confirmation_min_move | higher | 0.01 | 0.015 | 15.7672 | -1.4988 | 1.37 | 0.1522 |
| entry_window_end | higher | 180 | 240 | 18.409 | 1.143 | 1.3627 | 0.1495 |
| price_range_high | lower | 0.6 | 0.58 | 16.1484 | -1.1176 | 1.3717 | 0.1535 |
| stop_loss | lower | 0.35 | 0.3 | 16.7735 | -0.4925 | 1.3571 | 0.1446 |
| cross_buffer | lower | 0.02 | 0.015 | 17.266 | 0.0 | 1.4013 | 0.1634 |
