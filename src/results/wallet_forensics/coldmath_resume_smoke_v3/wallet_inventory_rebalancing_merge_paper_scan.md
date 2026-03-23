# Inventory Merge Paper Scan

## Overview
- Profile: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Strategy: `coldmath_inventory_rebalancing_merge_v2`
- Complete set threshold: `0.995`
- Active weather contexts loaded: `1`
- Markets evaluated: `11`
- Candidate count: `0`
- Near-miss count tracked: `11`

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
- `tel aviv` `2026-03-24` `16°C` | ask cost `1.0020` | size `n/a` | imbalance `n/a` | reasons `complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `14°C` | ask cost `1.0030` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `22°C` | ask cost `1.0030` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `23°C or higher` | ask cost `1.0030` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `13°C or below` | ask cost `1.0040` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `15°C` | ask cost `1.0040` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `21°C` | ask cost `1.0200` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `17°C` | ask cost `1.0300` | size `n/a` | imbalance `n/a` | reasons `complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `18°C` | ask cost `1.0400` | size `n/a` | imbalance `n/a` | reasons `complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`
- `tel aviv` `2026-03-24` `20°C` | ask cost `1.0500` | size `n/a` | imbalance `n/a` | reasons `stale_quote, complete_set_cost_above_threshold, missing_mergeable_size, missing_inventory_balance, no_midpoint_under_par_confirmation`

## Rejection Summary
- `complete_set_cost_above_threshold`: `11`
- `missing_inventory_balance`: `11`
- `missing_mergeable_size`: `11`
- `no_midpoint_under_par_confirmation`: `11`
- `stale_quote`: `7`
- `wide_leg_spread`: `1`

## Runtime Notes
- Sequence-level merge delay is still a post-entry runtime concern, not a pre-entry paper-scan filter.
- Historical fill-quality labels are approximated live with midpoint confirmation and spread guards, not measured directly.
- The historical worse-than-nearby-fill ratio cannot be observed pre-trade; the live scanner uses quote quality proxies instead.
