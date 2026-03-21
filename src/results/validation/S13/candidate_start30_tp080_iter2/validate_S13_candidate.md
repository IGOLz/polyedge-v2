# Validation: S13_feature_window=5_entry_window_start=30_entry_window_end=240_min_underlying_return=0.001_min_market_confirmation=0.0_max_market_delta=0.05_max_price_distance_from_mid=0.2_max_underlying_vol=0.006_stop_loss=0.25_take_profit=0.8

- Generated at: 2026-03-21T14:44:17.928761+00:00
- Strategy: S13
- Source: S13:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 233 |
| win_rate_pct | 88.84 |
| total_pnl | 27.649 |
| profit_factor | 3.9634 |
| sharpe_ratio | 0.6589 |
| max_drawdown | 1.3527 |
| eligible_markets | 10680 |
| accelerated | True |
| skipped_markets_missing_features | 932 |

## Candidate Parameters

| Parameter | Value |
| --- | --- |
| feature_window | 5 |
| entry_window_start | 30 |
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
| 0.0 | 233 | 29.9331 | 4.2996 | 0.7135 | 1.3033 |
| 0.01 | 233 | 27.649 | 3.9634 | 0.6589 | 1.3527 |
| 0.02 | 233 | 25.369 | 3.6456 | 0.6045 | 1.4022 |
| 0.03 | 233 | 23.0903 | 3.3448 | 0.5501 | 1.4516 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 233 | 27.649 | 3.9634 | 0.6589 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2670 | 7 | 0.9747 | 3.7396 | 0.6194 | 2026-03-14T00:45:00+00:00 | 2026-03-15T18:25:00+00:00 |
| 2 | 2670 | 133 | 14.5786 | 3.604 | 0.602 | 2026-03-15T18:25:00+00:00 | 2026-03-17T12:05:00+00:00 |
| 3 | 2670 | 55 | 7.4131 | 5.2179 | 0.8027 | 2026-03-17T12:10:00+00:00 | 2026-03-19T05:50:00+00:00 |
| 4 | 2670 | 38 | 4.6826 | 3.8931 | 0.6592 | 2026-03-19T05:50:00+00:00 | 2026-03-20T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 2669 | 46 | 6.1002 | 6.884 | 0.8951 |
| eth | 2669 | 84 | 10.1272 | 3.8265 | 0.6439 |
| sol | 2670 | 60 | 6.6807 | 3.324 | 0.5738 |
| xrp | 2672 | 43 | 4.7409 | 3.5823 | 0.6061 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 2672 | 125 | 11.9091 | 2.6381 | 0.4521 |
| 5m | 8008 | 108 | 15.7399 | 8.6391 | 1.1027 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 1 | 0.1248 | 124.839 | 124.839 |
| 2026-03-15 | 1536 | 26 | 4.5884 | 13.8966 | 1.4458 |
| 2026-03-16 | 1536 | 71 | 7.1185 | 3.1342 | 0.5279 |
| 2026-03-17 | 1536 | 63 | 6.7075 | 3.2253 | 0.5442 |
| 2026-03-18 | 1536 | 32 | 3.9716 | 4.9461 | 0.7658 |
| 2026-03-19 | 1521 | 29 | 4.6796 | 8.6541 | 1.125 |
| 2026-03-20 | 1527 | 11 | 0.4586 | 1.4554 | 0.1669 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 23.0526 |
| p50_total_pnl | 27.4404 |
| p95_total_pnl | 31.9092 |
| mean_total_pnl | 27.4135 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | lower | 0.001 | 0.0005 | 85.8894 | 58.2404 | 1.4685 | 0.1767 |
| min_underlying_return | higher | 0.001 | 0.0015 | 5.3632 | -22.2858 | 3.3719 | 0.5723 |
| max_market_delta | lower | 0.05 | 0.03 | 15.8357 | -11.8133 | 5.4051 | 0.8143 |
| feature_window | higher | 5 | 10 | 21.251 | -6.398 | 2.2142 | 0.3722 |
| entry_window_end | lower | 240 | 180 | 22.1577 | -5.4913 | 3.4472 | 0.5863 |
| entry_window_start | higher | 30 | 45 | 22.2359 | -5.4131 | 3.9175 | 0.647 |
| max_price_distance_from_mid | lower | 0.2 | 0.16 | 22.3275 | -5.3215 | 3.7857 | 0.6679 |
| take_profit | lower | 0.8 | 0.75 | 23.9635 | -3.6855 | 5.6164 | 0.7722 |
| min_market_confirmation | higher | 0.0 | 0.003 | 24.012 | -3.637 | 3.7858 | 0.6346 |
| entry_window_start | lower | 30 | 20 | 30.9783 | 3.3293 | 3.9469 | 0.6626 |
| max_market_delta | higher | 0.05 | 0.07 | 30.9525 | 3.3035 | 2.5651 | 0.4419 |
| stop_loss | higher | 0.25 | 0.3 | 25.6025 | -2.0465 | 3.5744 | 0.6162 |
| stop_loss | lower | 0.25 | 0.2 | 26.4095 | -1.2395 | 3.4986 | 0.5834 |
| max_underlying_vol | higher | 0.006 | 0.01 | 27.649 | 0.0 | 3.9634 | 0.6589 |
