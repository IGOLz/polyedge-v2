# S01: Parameter Grid Foundation — Research

**Date:** 2026-03-18

## Summary

S01 extends all 7 existing strategies (S1-S7) and TEMPLATE to include stop loss and take profit parameter ranges in their `get_param_grid()` return values. Each strategy currently returns a dict with entry parameter lists (e.g., `{"entry_window_start": [30, 45, 60], ...}`) producing 72-144 combinations per strategy. Adding `stop_loss` and `take_profit` keys multiplies the parameter space — with conservative ranges of 3 values each, this becomes 9× current size.

The existing infrastructure already supports the mechanics: `optimize.py` generates Cartesian products, `make_trade()` accepts `second_exited` and `exit_price` for mid-market exits, and the Trade dataclass has all necessary fields. S01 is purely about **declaring the parameter ranges** — the actual exit logic comes in S02, and grid generation integration in S03.

The work is straightforward: add two keys to each strategy's param grid dict, update TEMPLATE with comments demonstrating the pattern, and verify all strategies import cleanly with the new keys present.

## Recommendation

Add `stop_loss` and `take_profit` to all 7 strategy param grids with **conservative ranges** (3 values each) to keep parameter space explosion manageable. Use absolute price thresholds per D012. Make ranges strategy-specific per D013 — calibration strategies (S1) might need different thresholds than momentum strategies (S2).

For S1 (calibration mispricing), reasonable SL/TP ranges might be:
- `stop_loss: [0.35, 0.40, 0.45]` — exit if price drops to these absolute levels
- `take_profit: [0.65, 0.70, 0.75]` — exit if price rises to these absolute levels

Other strategies can use similar ranges tuned to their entry price expectations. TEMPLATE should demonstrate the pattern with clear comments explaining absolute vs relative semantics.

## Implementation Landscape

### Key Files

- `src/shared/strategies/S1/config.py` — S1 (calibration) param grid: add `stop_loss` and `take_profit` keys with 3 values each
- `src/shared/strategies/S2/config.py` — S2 (momentum) param grid: add SL/TP keys
- `src/shared/strategies/S3/config.py` — S3 (mean reversion) param grid: add SL/TP keys
- `src/shared/strategies/S4/config.py` — S4 (volatility regime) param grid: add SL/TP keys
- `src/shared/strategies/S5/config.py` — S5 (time-phase) param grid: add SL/TP keys
- `src/shared/strategies/S6/config.py` — S6 (streak) param grid: add SL/TP keys
- `src/shared/strategies/S7/config.py` — S7 (composite ensemble) param grid: add SL/TP keys
- `src/shared/strategies/TEMPLATE/config.py` — Update example grid with commented SL/TP keys explaining absolute price threshold semantics

All files follow the same pattern: the `get_param_grid()` function returns a dict with string keys mapping to lists of values. Adding two new keys is a direct extension.

### Build Order

1. **Update S1-S7 config files first** — Add `stop_loss` and `take_profit` keys to each strategy's `get_param_grid()` return dict. Start with S1, verify it doesn't break imports, then replicate pattern to S2-S7.

2. **Update TEMPLATE** — Add example SL/TP keys with comments explaining: (a) absolute price thresholds not relative offsets, (b) strategy should tune ranges based on entry price expectations, (c) invalid combinations (SL > TP for Up bets) will be skipped in S03.

3. **Write verification script** — `src/scripts/verify_m004_s01.py` that imports all S1-S7 config modules, calls `get_param_grid()`, and checks for presence of 'stop_loss' and 'take_profit' keys. Print grid sizes to confirm parameter explosion is manageable (target: <1000 combinations per strategy).

4. **Run verification** — Execute from `src/` directory with `PYTHONPATH=. python3 scripts/verify_m004_s01.py` and confirm all checks pass.

### Verification Approach

Success criteria:
- All S1-S7 config files import without errors
- Each `get_param_grid()` return value has 'stop_loss' and 'take_profit' keys
- Values are non-empty lists of floats
- Grid sizes are printed and reasonable (<1000 combinations per strategy)
- TEMPLATE has example SL/TP keys with clear comments

Command: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`

Expected output:
```
=== S01 Verification: Parameter Grid Foundation ===

1. S1 config
  [PASS] get_param_grid() has stop_loss key
  [PASS] get_param_grid() has take_profit key
  [PASS] stop_loss is non-empty list
  [PASS] take_profit is non-empty list
  Grid size: 108 entry combos × 3 SL × 3 TP = 972 total

2. S2 config
  [PASS] ...
  Grid size: 72 × 9 = 648 total

... [repeat for S3-S7] ...

8. TEMPLATE
  [PASS] get_param_grid() has stop_loss key
  [PASS] get_param_grid() has take_profit key
  [PASS] Example includes comments

All checks passed. S01 complete.
```

## Constraints

- **Parameter space explosion** — Current strategies have 72-144 combinations each. Adding SL/TP naively could create 10,000+ combinations if we're not conservative. Mitigation: Use 3 values per SL/TP (9× multiplier) to start. Can expand ranges in future if runtime permits.

- **No validation yet** — S01 just declares ranges; invalid combinations (e.g., SL > TP for Up bets) won't be filtered until S03. This is intentional per slice boundaries.

- **Strategy-specific ranges** — Each strategy's entry logic targets different price ranges. S1 (calibration) enters around 0.45/0.55, so SL/TP should reflect that. S3 (mean reversion) enters at spikes (0.80+), so different ranges. Each strategy needs tuned SL/TP ranges, not universal defaults.

- **Absolute thresholds** — Per D012, SL/TP are absolute prices (e.g., 0.40) not relative offsets (e.g., -0.05 from entry). This means a Down bet with entry=0.30, SL=0.35, TP=0.25 makes sense (SL higher, TP lower because we're shorting the Up token).

## Common Pitfalls

- **Copy-paste SL/TP ranges without adjustment** — Each strategy's entry prices differ. S1 enters at ~0.45 (low) or ~0.55 (high), S3 enters at ~0.80 (spike). Using the same SL/TP ranges for all strategies will produce nonsensical combinations. Tailor ranges to each strategy's typical entry prices.

- **Too many SL/TP values** — Adding 5 SL × 5 TP values (25× multiplier) to a strategy with 144 entry combos creates 3,600 total combinations. Runtime could be prohibitive. Start with 3×3 (9× multiplier) and expand only if results justify it.

- **Forgetting TEMPLATE** — Developers will copy TEMPLATE for new strategies. If TEMPLATE doesn't demonstrate SL/TP pattern with clear comments, future strategies will omit it. Make the example obvious and well-commented.

## Open Risks

None. This slice is low-risk: adding two keys to existing dicts with no behavior changes. The existing `optimize.py` already handles arbitrary param grid keys via `dict(zip(param_names, combo))` — it doesn't validate key names. S01 just declares the new keys; downstream slices wire them into the engine and grid generator.

## Sources

- Requirements R023 (strategies declare tunable parameters), R024 (SL/TP are universal exit parameters), R029 (all 7 strategies updated), R030 (TEMPLATE updated)
- Decision D012 (absolute price thresholds), D013 (strategy-specific ranges), D014 (skip invalid combinations)
- Current codebase: `src/shared/strategies/S1-S7/config.py` all have `get_param_grid()` returning dicts; `src/analysis/optimize.py` generates Cartesian products via `itertools.product(*param_values)`
