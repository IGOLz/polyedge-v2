# Validation: S5_entry_window_start=45_entry_window_end=240_allowed_hours=[18, 19, 20, 21, 22, 23]_price_range_low=0.45_price_range_high=0.6_approach_lookback=12_cross_buffer=0.015_confirmation_lookback=5_confirmation_min_move=0.01_min_cross_move=0.04_stop_loss=0.35_take_profit=0.7

- Generated at: 2026-03-19T22:15:19.028870+00:00
- Strategy: S5
- Source: results\optimization\S5\run_20260319_204940\Test_optimize_S5_Results.csv

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 1144 |
| win_rate_pct | 63.37 |
| total_pnl | 19.553 |
| profit_factor | 1.2105 |
| sharpe_ratio | 0.0926 |
| max_drawdown | 5.3529 |
| eligible_markets | 9029 |
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
| 0.0 | 1144 | 30.9168 | 1.3486 | 0.1464 | 3.3849 |
| 0.01 | 1144 | 19.553 | 1.2105 | 0.0926 | 5.3529 |
| 0.02 | 1144 | 8.1904 | 1.0844 | 0.0388 | 7.6463 |
| 0.03 | 1144 | -3.1629 | 0.9688 | -0.015 | 11.2075 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 1144 | 19.553 | 1.2105 | 0.0926 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1505 | 168 | 4.7246 | 1.3624 | 0.148 | 2026-03-14T00:45:00+00:00 | 2026-03-15T00:15:00+00:00 |
| 2 | 1505 | 188 | 2.8205 | 1.1808 | 0.0805 | 2026-03-15T00:15:00+00:00 | 2026-03-15T23:45:00+00:00 |
| 3 | 1505 | 177 | 5.7294 | 1.4579 | 0.1826 | 2026-03-15T23:45:00+00:00 | 2026-03-16T23:15:00+00:00 |
| 4 | 1505 | 193 | 4.9125 | 1.3301 | 0.1386 | 2026-03-16T23:15:00+00:00 | 2026-03-17T22:45:00+00:00 |
| 5 | 1505 | 199 | 3.8559 | 1.2499 | 0.1087 | 2026-03-17T22:45:00+00:00 | 2026-03-18T22:15:00+00:00 |
| 6 | 1504 | 219 | -2.49 | 0.8837 | -0.0599 | 2026-03-18T22:15:00+00:00 | 2026-03-19T22:00:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2257 | 306 | 2.3063 | 1.0905 | 0.0421 |
| eth | 2257 | 285 | 6.2312 | 1.2723 | 0.1168 |
| sol | 2258 | 269 | 6.6992 | 1.3188 | 0.1338 |
| xrp | 2257 | 284 | 4.3164 | 1.1837 | 0.0814 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2256 | 248 | 0.706 | 1.0327 | 0.0157 |
| 5m | 6773 | 896 | 18.847 | 1.2644 | 0.1134 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 168 | 4.7246 | 1.3624 | 0.148 |
| 2026-03-15 | 1536 | 194 | 3.3801 | 1.2137 | 0.0939 |
| 2026-03-16 | 1536 | 203 | 6.719 | 1.4648 | 0.1854 |
| 2026-03-17 | 1536 | 205 | 6.5684 | 1.4459 | 0.179 |
| 2026-03-18 | 1536 | 214 | -0.2164 | 0.9889 | -0.0054 |
| 2026-03-19 | 1397 | 160 | -1.6227 | 0.8944 | -0.0539 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 1000 |
| probability_positive_pct | 99.9 |
| p05_total_pnl | 9.2838 |
| p50_total_pnl | 19.6481 |
| p95_total_pnl | 29.7785 |
| mean_total_pnl | 19.6631 |
