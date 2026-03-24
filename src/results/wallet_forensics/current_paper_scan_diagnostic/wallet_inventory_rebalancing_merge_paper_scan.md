# Inventory Merge Paper Scan

## Overview
- Profile: `ColdMath`
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Strategy: `coldmath_inventory_rebalancing_merge_v2`
- Complete set threshold: `0.995`
- Active weather contexts loaded: `7`
- Markets evaluated: `77`
- Candidate count: `0`
- Near-miss count tracked: `20`

## Active Filters
- Require full quote pair: `True`
- Min mergeable size: `0.0`
- Max inventory imbalance ratio: `0.491617`
- Max quote age seconds: `600`
- Max leg spread: `0.05`
- Midpoint confirmation required: `True`

## Top Candidates
- No current weather markets satisfy the live merge filters.

## Near Misses
- `seoul` `2026-03-25` `5°C or below` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `6°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `7°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `8°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `9°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `10°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `11°C` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-26` `11°C or below` | ask cost `1.0010` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-25` `24°C or higher` | ask cost `1.0040` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `seoul` `2026-03-25` `12°C` | ask cost `1.0100` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`

## Rejection Summary
- `missing_inventory_balance`: `77`
- `missing_mergeable_size`: `77`
- `missing_complete_set_cost`: `44`
- `missing_full_quote_pair`: `44`
- `missing_leg_spread`: `44`
- `missing_midpoint_confirmation`: `44`
- `missing_pair_ask`: `44`
- `missing_quote_time`: `44`
- `complete_set_cost_above_threshold`: `33`
- `no_midpoint_under_par_confirmation`: `33`

## Runtime Notes
- Sequence-level merge delay is still a post-entry runtime concern, not a pre-entry paper-scan filter.
- Historical fill-quality labels are approximated live with midpoint confirmation and spread guards, not measured directly.
- The historical worse-than-nearby-fill ratio cannot be observed pre-trade; the live scanner uses quote quality proxies instead.
