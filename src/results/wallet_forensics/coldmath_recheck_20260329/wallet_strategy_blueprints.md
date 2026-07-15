# Strategy Blueprints: ColdMath

## Overview
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Blueprint count: `4`

## Blueprints
### inventory_rebalancing_merge
- Status: `ready_for_backtest`
- Confidence: `0.99`
- Priority: `260.08`
- Support count: `1083`
- Summary: Accumulate both sides in the same condition when the reconstructed complete-set cost is below par, keep inventory roughly balanced, and exit by merging back into collateral.
- Entry: `{"complete_set_cost_lte": 0.995, "condition": "same_condition_both_sides", "max_inventory_imbalance_ratio": 0.473218}`
- Sizing: `{"inventory_style": "match_smaller_side_and_rebalance", "matched_size_target": 94.523891}`
- Exit: `{"action": "merge", "expected_merge_delay_minutes": 0.733333, "when_inventory_matched": true}`
- Risk: `{"avoid_unmatched_inventory": true, "force_flatten_before_resolution": true, "max_complete_set_cost": 0.995}`

### neg_risk_basket
- Status: `needs_exit_research`
- Confidence: `0.94`
- Priority: `137.59`
- Support count: `430`
- Summary: Construct a same-side basket across sibling negative-risk markets when the basket cost is below a synthetic complete set, then monetize through event completion or later operational exits.
- Entry: `{"complete_set_cost_lte": 0.99, "condition": "neg_risk_event_basket", "min_distinct_conditions": 3}`
- Sizing: `{"inventory_style": "equal_notional_per_condition", "max_unmatched_ratio": 0.317073}`
- Exit: `{"action": "event_completion_or_conversion", "notes": "Needs explicit operational exit modeling beyond naive mark-to-market replay."}`
- Risk: `{"limit_unmatched_tail_inventory": true, "max_basket_cost": 0.995, "require_sibling_coverage": true}`

### dust_long_tail_bucket
- Status: `needs_exit_research`
- Confidence: `0.89`
- Priority: `26.55`
- Support count: `10`
- Summary: Pick up extremely low-priced tail buckets, likely as convex payoff scraps or as complements to a larger basket.
- Entry: `{"condition": "tail_bucket_pricing", "max_entry_price": 0.001}`
- Sizing: `{"inventory_style": "small_probe_or_basket_complement", "max_notional_per_bucket": 50.0}`
- Exit: `{"action": "research_required", "notes": "Standalone replay is weak; likely depends on basket context."}`
- Risk: `{"cap_total_tail_exposure": 0.1, "treat_as_add_on_only": true}`

### late_redemption_farming
- Status: `operational_only`
- Confidence: `0.91`
- Priority: `85.74`
- Support count: `45`
- Summary: Hold winning inventory through resolution and redeem directly, treating redemption as an operational exit path rather than alpha by itself.
- Entry: `{"condition": "no_entry_signal"}`
- Sizing: `{"inventory_style": "inherits_primary_strategy_position"}`
- Exit: `{"action": "redeem_after_resolution"}`
- Risk: `{"require_verified_resolution": true}`

