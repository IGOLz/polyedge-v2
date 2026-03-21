# Validation: S13_feature_window=5_entry_window_start=20_entry_window_end=240_min_underlying_return=0.001_min_market_confirmation=0.0_max_market_delta=0.05_max_price_distance_from_mid=0.2_max_underlying_vol=0.006_stop_loss=0.25_take_profit=0.8

- Generated at: 2026-03-21T14:23:30.052718+00:00
- Strategy: S13
- Source: S13:candidate

## Overall

| Metric | Value |
| --- | --- |
| total_bets | 218 |
| win_rate_pct | 88.53 |
| total_pnl | 25.8401 |
| profit_factor | 3.9055 |
| sharpe_ratio | 0.6543 |
| max_drawdown | 1.6112 |
| eligible_markets | 11592 |
| accelerated | True |
| skipped_markets_missing_features | 0 |

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
| 0.0 | 218 | 27.9771 | 4.2363 | 0.7085 | 1.5715 |
| 0.01 | 218 | 25.8401 | 3.9055 | 0.6543 | 1.6112 |
| 0.02 | 218 | 23.7054 | 3.5929 | 0.6001 | 1.6509 |
| 0.03 | 218 | 21.5732 | 3.2972 | 0.546 | 1.6906 |

## Entry Delay Sweep

| Delay(s) | Bets | PnL | PF | Sharpe | MissedEntries |
| --- | --- | --- | --- | --- | --- |
| 0 | 218 | 25.8401 | 3.9055 | 0.6543 | 0 |

## Chronological Folds

| Fold | Markets | Bets | PnL | PF | Sharpe | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1908 | 7 | 0.9853 | 3.7694 | 0.6238 | 2026-03-14T00:45:00+00:00 | 2026-03-15T06:30:00+00:00 |
| 2 | 1908 | 48 | 7.0816 | 6.0231 | 0.9141 | 2026-03-15T06:30:00+00:00 | 2026-03-16T12:15:00+00:00 |
| 3 | 1908 | 121 | 11.523 | 2.8824 | 0.4909 | 2026-03-16T12:20:00+00:00 | 2026-03-17T18:05:00+00:00 |
| 4 | 1908 | 42 | 6.2502 | 7.21 | 0.9883 | 2026-03-17T18:10:00+00:00 | 2026-03-18T23:55:00+00:00 |

## Asset Slices

| Asset | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| btc | 1908 | 40 | 4.9602 | 5.6127 | 0.8034 |
| eth | 1908 | 74 | 9.2902 | 4.247 | 0.6975 |
| sol | 1908 | 57 | 6.2777 | 3.2065 | 0.5556 |
| xrp | 1908 | 47 | 5.312 | 3.5151 | 0.6026 |

## Duration Slices

| Duration | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 15m | 1908 | 108 | 10.5319 | 2.6953 | 0.4638 |
| 5m | 5724 | 110 | 15.3082 | 6.7096 | 0.9584 |

## Day Slices

| Day | Markets | Bets | PnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | 1488 | 2 | 0.3781 | 378.141 | 2.0814 |
| 2026-03-15 | 1536 | 28 | 4.5254 | 7.4499 | 1.0462 |
| 2026-03-16 | 1536 | 80 | 7.9858 | 3.0707 | 0.5269 |
| 2026-03-17 | 1536 | 70 | 7.628 | 3.2915 | 0.5585 |
| 2026-03-18 | 1536 | 38 | 5.3227 | 6.2885 | 0.9011 |

## Exit Reasons

Exit reasons are omitted in accelerated mode to keep validation fast.

## Bootstrap Robustness

| Metric | Value |
| --- | --- |
| iterations | 300 |
| probability_positive_pct | 100.0 |
| p05_total_pnl | 21.4202 |
| p50_total_pnl | 25.8496 |
| p95_total_pnl | 30.0339 |
| mean_total_pnl | 25.8443 |

## Parameter Neighbors

| Parameter | Direction | Candidate | Neighbor | PnL | DeltaPnL | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_underlying_return | lower | 0.001 | 0.0005 | 65.8598 | 40.0197 | 1.4341 | 0.1668 |
| min_underlying_return | higher | 0.001 | 0.0015 | 6.3406 | -19.4995 | 5.1969 | 0.7956 |
| max_market_delta | lower | 0.05 | 0.03 | 16.4048 | -9.4353 | 5.974 | 0.8678 |
| feature_window | higher | 5 | 10 | 18.9192 | -6.9209 | 2.1871 | 0.3662 |
| max_price_distance_from_mid | lower | 0.2 | 0.16 | 20.754 | -5.0861 | 3.7387 | 0.664 |
| entry_window_end | lower | 240 | 180 | 20.7653 | -5.0748 | 3.3349 | 0.5702 |
| min_market_confirmation | higher | 0.0 | 0.003 | 21.9081 | -3.932 | 3.5481 | 0.6035 |
| entry_window_start | higher | 20 | 30 | 22.5108 | -3.3293 | 3.919 | 0.6488 |
| max_market_delta | higher | 0.05 | 0.07 | 29.0097 | 3.1696 | 2.7096 | 0.4715 |
| take_profit | lower | 0.8 | 0.75 | 22.7322 | -3.1079 | 5.6835 | 0.7852 |
| stop_loss | higher | 0.25 | 0.3 | 24.3638 | -1.4763 | 3.6591 | 0.6316 |
| stop_loss | lower | 0.25 | 0.2 | 24.6488 | -1.1913 | 3.4442 | 0.578 |
| entry_window_start | lower | 20 | 10 | 24.7902 | -1.0499 | 3.0735 | 0.5363 |
| max_underlying_vol | higher | 0.006 | 0.01 | 25.8401 | 0.0 | 3.9055 | 0.6543 |
