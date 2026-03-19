# Validation: S5_entry_window_start=45_entry_window_end=240_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.015_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:19:43.780918+00:00
- Strategy: S5
- Source: results\optimization\S5\run_20260319_204940\Test_optimize_S5_Results.csv

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 899 |
| win_rate_pct | 64.85 |
| total_pnl | 19.3025 |
| profit_factor | 1.2708 |
| sharpe_ratio | 0.1158 |
| max_drawdown | 3.6074 |
| eligible_markets | 6777 |
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
| 0.0 | 899 | 28.2307 | 1.4144 | 0.1694 | 2.8081 |
| 0.01 | 899 | 19.3025 | 1.2708 | 0.1158 | 3.6074 |
| 0.02 | 899 | 10.3757 | 1.1394 | 0.0623 | 4.8983 |
| 0.03 | 899 | 1.4574 | 1.0188 | 0.0087 | 6.9619 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 899 | 19.3025 | 1.2708 | 0.1158 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1130 | 129 | 5.3623 | 1.584 | 0.2195 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 1130 | 151 | 1.8549 | 1.143 | 0.0645 | 2026-03-15T00:15:00+00:00 | 2026-03-15T23:45:00+00:00 |
| 3 | 1130 | 136 | 4.7336 | 1.4965 | 0.1946 | 2026-03-15T23:50:00+00:00 | 2026-03-16T23:20:00+00:00 |
| 4 | 1129 | 150 | 3.9374 | 1.34 | 0.1416 | 2026-03-16T23:20:00+00:00 | 2026-03-17T22:50:00+00:00 |
| 5 | 1129 | 159 | 4.1306 | 1.3492 | 0.1454 | 2026-03-17T22:50:00+00:00 | 2026-03-18T22:20:00+00:00 |
| 6 | 1129 | 174 | -0.7163 | 0.9557 | -0.0219 | 2026-03-18T22:25:00+00:00 | 2026-03-19T22:05:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 1694 | 247 | 1.0935 | 1.0523 | 0.0247 |
| eth | 1694 | 221 | 4.8814 | 1.2719 | 0.1162 |
| sol | 1695 | 211 | 8.2018 | 1.5476 | 0.2111 |
| xrp | 1694 | 220 | 5.1257 | 1.2942 | 0.124 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 6777 | 899 | 19.3025 | 1.2708 | 0.1158 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1116 | 129 | 5.3623 | 1.584 | 0.2195 |
| 2026-03-15 | 1152 | 153 | 2.1884 | 1.1687 | 0.0753 |
| 2026-03-16 | 1152 | 156 | 5.8071 | 1.5329 | 0.2069 |
| 2026-03-17 | 1152 | 162 | 5.24 | 1.4525 | 0.1805 |
| 2026-03-18 | 1152 | 169 | 0.1608 | 1.0105 | 0.0051 |
| 2026-03-19 | 1053 | 130 | 0.5439 | 1.0481 | 0.0226 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 10.4533 |
| p50_total_pnl | 19.0414 |
| p95_total_pnl | 28.0614 |
| mean_total_pnl | 19.1369 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | -2.9673 | -22.2698 | 0.969 | -0.0152 |
| entry_window_start | higher | 45 | 60 | 11.768 | -7.5345 | 1.1676 | 0.0747 |
| take_profit | lower | 0.7 | 0.65 | 11.9606 | -7.3419 | 1.2075 | 0.086 |
| price_range_low | higher | 0.45 | 0.47 | 14.5128 | -4.7897 | 1.2077 | 0.0912 |
| stop_loss | lower | 0.35 | 0.3 | 16.1093 | -3.1932 | 1.2029 | 0.0872 |
| confirmation_lookback | lower | 5 | 3 | 16.803 | -2.4995 | 1.2335 | 0.1014 |
| approach_lookback | lower | 12 | 8 | 17.2732 | -2.0293 | 1.2451 | 0.106 |
| entry_window_end | lower | 240 | 180 | 17.6391 | -1.6634 | 1.2874 | 0.1224 |
| min_cross_move | higher | 0.04 | 0.05 | 17.7755 | -1.527 | 1.2497 | 0.1076 |
| confirmation_min_move | higher | 0.01 | 0.015 | 18.1345 | -1.168 | 1.2565 | 0.1102 |
| price_range_high | lower | 0.6 | 0.58 | 18.7471 | -0.5554 | 1.2638 | 0.1136 |
| cross_buffer | higher | 0.015 | 0.02 | 19.3025 | 0.0 | 1.2708 | 0.1158 |
