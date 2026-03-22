# EVPOLY Strategy Research

## What EVPOLY Is Doing Well

- It separates signal timing from execution and risk controls.
- It is heavily checkpoint-driven instead of scanning every second with the same rules.
- It avoids trading near the base anchor unless the move is strong and persistent.
- It uses price caps aggressively instead of blindly paying any token price.
- It treats trigger-style markets and late-window markets as different families.

## What We Can Reuse In `polyedge-v2`

- Checkpoint logic from `evcurve_v1`.
- Late-window continuation from `endgame_sweep_v1`.
- Final-seconds price-band gating from `sessionband_v1`.
- Trigger-cross logic from `evsnipe_v1`.
- Early opening-drive accumulation as the closest backtestable analogue to `premarket_v1`.

## What We Cannot Reuse Directly

- Remote alpha endpoints. EVPOLY relies on hosted decision services for a lot of live directionality.
- Orderbook-depth and stale-quote guards. Our current backtest dataset does not carry the same microstructure detail.
- True pre-open ladders. Our market snapshots begin after market open, so we cannot simulate actual premarket resting orders.
- MM strategies. `mm_rewards_v1` and `mm_sport_v1` need inventory and orderbook state that this backtest engine does not model.

## New Backtestable Ports

- `S20`: EVcurve-inspired checkpoint continuation when the underlying is ahead of Polymarket.
- `S21`: Endgame-inspired late sweep continuation with recent impulse confirmation.
- `S22`: SessionBand-inspired final-seconds price-band filter.
- `S23`: EVSnipe-inspired trigger-cross entry on open-to-now return thresholds.
- `S24`: Premarket-inspired opening-drive accumulation after the market opens.
- `S25`: S20-lite checkpoint drift follow using only 5-second relative features plus trade-count confirmation.

## Why These Ports Fit The Current Engine

- Every strategy uses only features already available in `polyedge-v2`.
- Every strategy has an accelerated optimizer kernel, so fast grid search still works.
- The live-only EVPOLY components were translated into deterministic feature rules instead of copied as black boxes.
