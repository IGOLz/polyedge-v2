# Validation: S13_feature_window=5_entry_window_start=20_entry_window_end=240_min_underlying_return=0.001_min_market_confirmation=0.0_max_market_delta=0.05_max_price_distance_from_mid=0.2_max_underlying_vol=0.006_stop_loss=0.25_take_profit=0.8

- Generated at: 2026-03-21T15:03:00.881379+00:00
- Strategy: S13
- Source: S13:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 123 |
| win_rate_pct | 93.5 |
| total_pnl | 17.6357 |
| profit_factor | 7.5777 |
| sharpe_ratio | 1.0328 |
| max_drawdown | 0.7036 |
| eligible_markets | 8008 |
| accelerated | True |
| skipped_markets_missing_features | 708 |

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
| 0.0 | 123 | 18.8393 | 8.242 | 1.1034 | 0.6544 |
| 0.01 | 123 | 17.6357 | 7.5777 | 1.0328 | 0.7036 |
| 0.02 | 123 | 16.4346 | 6.9527 | 0.9624 | 0.7528 |
| 0.03 | 123 | 15.2339 | 6.363 | 0.8919 | 0.802 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 123 | 17.6357 | 7.5777 | 1.0328 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2002 | 4 | 0.8054 | 805.397 | 3.1928 | 2026-03-14T00:45:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 2002 | 76 | 9.6473 | 5.1824 | 0.8164 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:05:00+00:00 |
| 3 | 2002 | 31 | 5.0684 | 14.5332 | 1.3606 | 2026-03-17T12:10:00+00:00 | 2026-03-19T05:50:00+00:00 |
| 4 | 2002 | 12 | 2.1147 | 2114.657 | 3.2133 | 2026-03-19T05:50:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2001 | 30 | 4.6213 | 14.4103 | 1.3328 |
| eth | 2001 | 45 | 5.755 | 5.356 | 0.8243 |
| sol | 2002 | 25 | 4.0478 | 13.0503 | 1.4241 |
| xrp | 2004 | 23 | 3.2117 | 5.7268 | 0.8666 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 5m | 8008 | 123 | 17.6357 | 7.5777 | 1.0328 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1116 | 2 | 0.3781 | 378.141 | 2.0814 |
| 2026-03-15 | 1152 | 10 | 1.7826 | 1782.588 | 3.686 |
| 2026-03-16 | 1152 | 47 | 4.9389 | 3.4687 | 0.5916 |
| 2026-03-17 | 1152 | 33 | 5.5302 | 19.0715 | 1.5932 |
| 2026-03-18 | 1152 | 18 | 2.6784 | 8.1516 | 1.0221 |
| 2026-03-19 | 1141 | 10 | 1.8505 | 1850.483 | 3.7291 |
| 2026-03-20 | 1143 | 3 | 0.4771 | 477.104 | 2.184 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 14.6804 |
| p50_total_pnl | 17.7876 |
| p95_total_pnl | 20.0824 |
| mean_total_pnl | 17.6314 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | lower | 0.001 | 0.0005 | 71.5237 | 53.888 | 1.7602 | 0.2596 |
| min_underlying_return | higher | 0.001 | 0.0015 | 4.438 | -13.1977 | 4437.981 | 3.8438 |
| max_market_delta | lower | 0.05 | 0.03 | 10.3926 | -7.2431 | 16.7321 | 1.5101 |
| max_price_distance_from_mid | lower | 0.2 | 0.16 | 13.4199 | -4.2158 | 6.0053 | 0.9399 |
| feature_window | higher | 5 | 10 | 13.4915 | -4.1442 | 2.8947 | 0.5071 |
| take_profit | lower | 0.8 | 0.75 | 14.7436 | -2.8921 | 9.599 | 1.0686 |
| entry_window_end | lower | 240 | 180 | 14.9734 | -2.6623 | 6.5847 | 0.9451 |
| min_market_confirmation | higher | 0.0 | 0.003 | 15.2576 | -2.3781 | 6.6907 | 0.9588 |
| max_market_delta | higher | 0.05 | 0.07 | 19.7281 | 2.0924 | 4.2415 | 0.7022 |
| entry_window_start | higher | 20 | 30 | 15.7399 | -1.8958 | 8.6391 | 1.1027 |
| stop_loss | higher | 0.25 | 0.3 | 16.4178 | -1.2179 | 6.1992 | 0.934 |
| stop_loss | lower | 0.25 | 0.2 | 17.2289 | -0.4068 | 6.5794 | 0.9321 |
| entry_window_start | lower | 20 | 10 | 18.0332 | 0.3975 | 5.4493 | 0.8475 |
| max_underlying_vol | higher | 0.006 | 0.01 | 17.6357 | 0.0 | 7.5777 | 1.0328 |
