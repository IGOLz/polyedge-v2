---
id: T01
parent: S02
milestone: M003
provides:
  - polymarket_dynamic_fee() function implementing Polymarket's dynamic fee formula
  - PnL calculation functions using dynamic fees instead of flat 2% rate
key_files:
  - src/analysis/backtest/engine.py
key_decisions:
  - Decision to use base_rate=0.063 as default (produces 3.15% peak fee at 50-cent prices, matching Polymarket's observed fee structure)
  - Decision to calculate fees on entry_price (the price paid) not exit_price, per Polymarket's fee-on-purchase model
patterns_established:
  - Dynamic fee calculation pattern: base_rate × min(price, 1 - price) for progressive fee scaling based on market confidence
observability_surfaces:
  - Trade.pnl field reflects dynamic fees (no distinguishing metadata — fee model is global engine setting)
duration: 15m
verification_result: passed
completed_at: 2026-03-18T13:58:36+01:00
blocker_discovered: false
---

# T01: Implement dynamic fee formula and update PnL calculations

**Replaced flat 2% fee with Polymarket dynamic fee model (base_rate × min(price, 1-price)) in all PnL calculations**

## What Happened

Added `polymarket_dynamic_fee()` function to `engine.py` implementing the formula `base_rate × min(price, 1 - price)` with default `base_rate=0.063`. Updated both `calculate_pnl_hold()` and `calculate_pnl_exit()` to call this function with `entry_price` instead of applying a flat `fee_rate`. Changed function signatures from `fee_rate=DEFAULT_FEE_RATE` to `base_rate=0.063` throughout. The dynamic fee model reflects Polymarket's actual CLOB fee structure: fees peak at ~3.15% for balanced markets (50-cent tokens) and drop to ~0.63% for confident outcomes (10-cent or 90-cent tokens).

Formula verification confirmed correct behavior:
- Fee at price=0.50: 0.0315 (3.15%)
- Fee at price=0.10: 0.0063 (0.63%)
- Fee at price=0.90: 0.0063 (0.63%)

Price clamping to [0.0, 1.0] handles invalid inputs gracefully.

## Verification

Ran automated verification script from task plan:
```bash
cd src && python3 << 'EOF'
from analysis.backtest.engine import polymarket_dynamic_fee
fee_50 = polymarket_dynamic_fee(0.50, 0.063)
fee_10 = polymarket_dynamic_fee(0.10, 0.063)
fee_90 = polymarket_dynamic_fee(0.90, 0.063)
assert abs(fee_50 - 0.0315) < 0.0001, f"Fee at 0.50 should be 0.0315, got {fee_50}"
assert abs(fee_10 - 0.0063) < 0.0001, f"Fee at 0.10 should be 0.0063, got {fee_10}"
assert abs(fee_90 - 0.0063) < 0.0001, f"Fee at 0.90 should be 0.0063, got {fee_90}"
print("✓ Dynamic fee formula verified")
EOF
```

All assertions passed. Also verified price clamping for out-of-range inputs (negative prices and prices > 1.0) produces valid fees.

Manual inspection confirmed:
- ✅ `polymarket_dynamic_fee()` exists with correct formula and documentation
- ✅ `calculate_pnl_hold()` calls it with `entry_price` and `base_rate`
- ✅ `calculate_pnl_exit()` calls it with `entry_price` and `base_rate`
- ✅ `make_trade()` uses `base_rate` parameter instead of `fee_rate`
- ✅ All signatures changed from `fee_rate` to `base_rate`

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | Formula correctness test (0.50, 0.10, 0.90 prices) | 0 | ✅ pass | <1s |
| 2 | Invalid input handling (price clamping) | 0 | ✅ pass | <1s |

## Diagnostics

No new diagnostic surfaces added. The `Trade.pnl` field will reflect dynamic fees after this change, but there's no per-trade metadata to distinguish whether dynamic or flat fees were used — the fee model is a global engine setting. To inspect fee impact, compare backtest results before/after this change (T02 will wire in CLI controls for this).

## Deviations

None — implementation followed task plan exactly.

## Known Issues

None. The implementation is complete and verified. T02 will add slippage modeling and wire these parameters through the CLI.

## Files Created/Modified

- `src/analysis/backtest/engine.py` — Added `polymarket_dynamic_fee()` function; updated `calculate_pnl_hold()`, `calculate_pnl_exit()`, and `make_trade()` to use dynamic fees with `base_rate` parameter instead of flat `fee_rate`
