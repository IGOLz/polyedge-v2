# Validation: S5_entry_window_start=45_entry_window_end=240_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.015_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:21:13.600345+00:00
- Strategy: S5
- Source: results\optimization\S5\run_20260319_204940\Test_optimize_S5_Results.csv

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 652 |
| win_rate_pct | 66.41 |
| total_pnl | 18.209 |
| profit_factor | 1.3616 |
| sharpe_ratio | 0.1491 |
| max_drawdown | 2.9185 |
| eligible_markets | 5083 |
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
| 0.0 | 652 | 24.6831 | 1.5124 | 0.2022 | 2.1831 |
| 0.01 | 652 | 18.209 | 1.3616 | 0.1491 | 2.9185 |
| 0.02 | 652 | 11.7362 | 1.2234 | 0.0961 | 3.6541 |
| 0.03 | 652 | 5.2699 | 1.0963 | 0.0432 | 4.4872 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 652 | 18.209 | 1.3616 | 0.1491 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 848 | 95 | 3.3646 | 1.4557 | 0.1787 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 847 | 109 | 2.1325 | 1.2326 | 0.1008 | 2026-03-15T00:15:00+00:00 | 2026-03-15T23:45:00+00:00 |
| 3 | 847 | 100 | 5.1163 | 1.8128 | 0.2885 | 2026-03-15T23:50:00+00:00 | 2026-03-16T23:20:00+00:00 |
| 4 | 847 | 109 | 3.77 | 1.4781 | 0.1885 | 2026-03-16T23:20:00+00:00 | 2026-03-17T22:50:00+00:00 |
| 5 | 847 | 112 | 3.6231 | 1.444 | 0.1788 | 2026-03-17T22:50:00+00:00 | 2026-03-18T22:20:00+00:00 |
| 6 | 847 | 127 | 0.2025 | 1.0177 | 0.0084 | 2026-03-18T22:25:00+00:00 | 2026-03-19T22:05:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| eth | 1694 | 221 | 4.8814 | 1.2719 | 0.1162 |
| sol | 1695 | 211 | 8.2018 | 1.5476 | 0.2111 |
| xrp | 1694 | 220 | 5.1257 | 1.2942 | 0.124 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 5083 | 652 | 18.209 | 1.3616 | 0.1491 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 837 | 95 | 3.3646 | 1.4557 | 0.1787 |
| 2026-03-15 | 864 | 111 | 2.4659 | 1.269 | 0.1149 |
| 2026-03-16 | 864 | 115 | 5.3397 | 1.6999 | 0.2574 |
| 2026-03-17 | 864 | 116 | 5.2947 | 1.711 | 0.26 |
| 2026-03-18 | 864 | 119 | 0.7471 | 1.0702 | 0.0329 |
| 2026-03-19 | 790 | 96 | 0.9969 | 1.1234 | 0.0557 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 99.9 |
| p05_total_pnl | 10.4889 |
| p50_total_pnl | 18.6011 |
| p95_total_pnl | 26.1558 |
| mean_total_pnl | 18.3288 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allowed_hours | lower | [18, 19, 20, 21, 22, 23] | [13, 14, 15, 16, 17, 18] | 1.3111 | -16.8979 | 1.019 | 0.0091 |
| take_profit | lower | 0.7 | 0.65 | 10.3226 | -7.8864 | 1.2492 | 0.101 |
| entry_window_start | higher | 45 | 60 | 10.4115 | -7.7975 | 1.2054 | 0.0899 |
| approach_lookback | lower | 12 | 8 | 14.5638 | -3.6452 | 1.2841 | 0.1207 |
| confirmation_lookback | lower | 5 | 3 | 14.8243 | -3.3847 | 1.2853 | 0.1212 |
| price_range_low | higher | 0.45 | 0.47 | 15.6448 | -2.5642 | 1.3249 | 0.136 |
| stop_loss | lower | 0.35 | 0.3 | 15.833 | -2.376 | 1.2826 | 0.1176 |
| min_cross_move | higher | 0.04 | 0.05 | 16.0307 | -2.1783 | 1.3135 | 0.1316 |
| confirmation_min_move | higher | 0.01 | 0.015 | 16.5748 | -1.6342 | 1.3298 | 0.1375 |
| entry_window_end | lower | 240 | 180 | 17.3305 | -0.8785 | 1.4067 | 0.1653 |
| price_range_high | lower | 0.6 | 0.58 | 17.7852 | -0.4238 | 1.3546 | 0.1472 |
| cross_buffer | higher | 0.015 | 0.02 | 18.209 | 0.0 | 1.3616 | 0.1491 |
