# S02: Engine upgrades — dynamic fees + slippage

**Goal:** Upgrade backtest engine from flat 2% fees to Polymarket's dynamic fee model (`baseRate × min(price, 1-price)`) and add configurable slippage penalty to entry prices. Make fees and slippage configurable via CLI flags.

**Demo:** Run the same strategy with `--slippage 0` vs `--slippage 0.01` and observe different PnL. Run with `--fee-base-rate 0.063` and confirm fee at price=0.50 is ~3.15% while fee at price=0.10 is ~0.63%.

## Must-Haves

- `polymarket_dynamic_fee(price, base_rate)` function implementing `base_rate × min(price, 1-price)`
- `calculate_pnl_hold()` and `calculate_pnl_exit()` use dynamic fees instead of flat `fee_rate`
- `make_trade()` accepts `slippage` parameter and adjusts entry price before PnL calculation (Up bets: +slippage, Down bets: -slippage)
- `backtest_strategies.py` accepts `--slippage` and `--fee-base-rate` CLI flags and passes them to `make_trade()`
- Backward compatibility: default `slippage=0.0` and `base_rate=0.063` (matching peak 3.15% at 50/50 prices)
- Adjusted entry prices clamped to [0.01, 0.99] to stay within valid token price range
- Fee calculation uses entry price (the price paid), not exit price

## Proof Level

- This slice proves: **contract + integration**
- Real runtime required: yes (run backtest with different parameters)
- Human/UAT required: no (verification is mechanical — formula correctness + PnL differences)

## Verification

Run these commands from `src/`:

```bash
# 1. Verify dynamic fee formula correctness
python3 << 'EOF'
from analysis.backtest.engine import polymarket_dynamic_fee
fee_50 = polymarket_dynamic_fee(0.50, 0.063)
fee_10 = polymarket_dynamic_fee(0.10, 0.063)
fee_90 = polymarket_dynamic_fee(0.90, 0.063)
assert abs(fee_50 - 0.0315) < 0.0001, f"Fee at 0.50 should be 0.0315, got {fee_50}"
assert abs(fee_10 - 0.0063) < 0.0001, f"Fee at 0.10 should be 0.0063, got {fee_10}"
assert abs(fee_90 - 0.0063) < 0.0001, f"Fee at 0.90 should be 0.0063, got {fee_90}"
print("✓ Dynamic fee formula verified")
EOF

# 2. Verify slippage impact on PnL (requires at least one strategy to exist)
# Run with zero slippage
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.0 > /tmp/no_slippage.txt 2>&1

# Run with 1-cent slippage
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.01 > /tmp/with_slippage.txt 2>&1

# Verify PnL differs
diff -u /tmp/no_slippage.txt /tmp/with_slippage.txt | grep -E '(total_pnl|PnL=)' && echo "✓ Slippage changes PnL as expected" || echo "✗ Slippage did not affect PnL"

# 3. Verify CLI flags are accepted without error
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.01 --fee-base-rate 0.05 > /dev/null 2>&1 && echo "✓ CLI flags accepted" || echo "✗ CLI flags rejected"

# 4. Verify error handling for invalid inputs (diagnostic check)
python3 << 'EOF'
from analysis.backtest.engine import polymarket_dynamic_fee

# Test price clamping for out-of-range values
fee_negative = polymarket_dynamic_fee(-0.5, 0.063)
fee_over_one = polymarket_dynamic_fee(1.5, 0.063)

# Both should be clamped and produce valid fees (0.0 or near-zero)
assert fee_negative >= 0.0 and fee_negative <= 0.05, f"Negative price should clamp to valid range, got fee {fee_negative}"
assert fee_over_one >= 0.0 and fee_over_one <= 0.05, f"Price > 1.0 should clamp to valid range, got fee {fee_over_one}"

print("✓ Invalid input handling verified (price clamping works)")
EOF
```

**Acceptance criteria:**
- All four verification commands pass
- Fee formula produces correct values at 0.50, 0.10, 0.90
- Invalid price inputs are clamped and produce valid fees
- Running with different slippage values produces different PnL
- CLI accepts both new flags without error

## Observability / Diagnostics

- Runtime signals: none (pure calculation, no async/state)
- Inspection surfaces: Trade objects contain `entry_price` and `pnl` fields; logs show per-strategy trade count and metrics
- Failure visibility: If fee formula is wrong, backtest metrics will be systematically off; if slippage is wrong, comparing zero vs non-zero slippage runs will show unexpected results
- Redaction constraints: none (no secrets involved)

## Integration Closure

- Upstream surfaces consumed:
  - `analysis.backtest.data_loader` — provides market dicts
  - `analysis.backtest_strategies.py` — CLI entry point that calls `make_trade()`
  - Existing `engine.py` functions: `calculate_pnl_hold()`, `calculate_pnl_exit()`, `make_trade()`
- New wiring introduced in this slice:
  - `polymarket_dynamic_fee()` called by PnL functions
  - `slippage` and `base_rate` parameters passed from CLI through `run_strategy()` to `make_trade()`
- What remains before the milestone is truly usable end-to-end:
  - S03 must implement real strategies that produce trades
  - S04 must document how to interpret fee/slippage impact in the operator playbook

## Tasks

- [x] **T01: Implement dynamic fee formula and update PnL calculations** `est:45m`
  - Why: R016 requires dynamic fees; this is the foundational math that everything else depends on
  - Files: `src/analysis/backtest/engine.py`
  - Do:
    1. Add `polymarket_dynamic_fee(price: float, base_rate: float = 0.063) -> float` function at module level (below imports, above Trade dataclass):
       - Formula: `return base_rate * min(price, 1.0 - price)`
       - Clamp price to [0.0, 1.0] for safety
    2. Update `calculate_pnl_hold()`:
       - Replace `fee_rate * gross` with `polymarket_dynamic_fee(entry_price, base_rate) * gross`
       - Change signature: replace `fee_rate=DEFAULT_FEE_RATE` with `base_rate=0.063`
       - Keep the logic identical: win = gross - fee, loss = -entry_price
    3. Update `calculate_pnl_exit()`:
       - Replace `fee_rate * max(0.0, gross)` with `polymarket_dynamic_fee(entry_price, base_rate) * max(0.0, gross)`
       - Change signature: replace `fee_rate=DEFAULT_FEE_RATE` with `base_rate=0.063`
    4. Test the formula in a Python REPL (from src/):
       ```python
       from analysis.backtest.engine import polymarket_dynamic_fee
       print(f"Fee at 0.50: {polymarket_dynamic_fee(0.50, 0.063):.4f}")  # expect 0.0315
       print(f"Fee at 0.10: {polymarket_dynamic_fee(0.10, 0.063):.4f}")  # expect 0.0063
       print(f"Fee at 0.90: {polymarket_dynamic_fee(0.90, 0.063):.4f}")  # expect 0.0063
       ```
  - Verify: Run the REPL test commands above; all three outputs must match expected values within 0.0001
  - Done when: `polymarket_dynamic_fee()` exists, PnL functions call it, and REPL test shows correct fee values

- [ ] **T02: Add slippage modeling and wire CLI parameters** `est:45m`
  - Why: R017 requires slippage; this completes the engine upgrade and exposes control to users
  - Files: `src/analysis/backtest/engine.py`, `src/analysis/backtest_strategies.py`
  - Do:
    1. Update `make_trade()` in `engine.py`:
       - Add parameters: `slippage: float = 0.0, base_rate: float = 0.063`
       - Before calling PnL functions, adjust entry_price:
         ```python
         adjusted_entry = entry_price
         if slippage != 0.0:
             if direction == "Up":
                 adjusted_entry = entry_price + slippage
             else:  # Down
                 adjusted_entry = entry_price - slippage
             adjusted_entry = max(0.01, min(0.99, adjusted_entry))
         ```
       - Pass `adjusted_entry` (instead of `entry_price`) and `base_rate` to `calculate_pnl_hold()` and `calculate_pnl_exit()`
       - Store original `entry_price` in the Trade object (not adjusted), so reports show what the strategy detected
       - Remove `fee_rate` parameter entirely (breaking change but acceptable — old code using it can pass `base_rate` instead)
    2. Update `run_strategy()` in `backtest_strategies.py`:
       - Add parameters: `slippage: float = 0.0, base_rate: float = 0.063`
       - Pass them to `make_trade()` call:
         ```python
         trade = make_trade(
             market,
             second_entered,
             signal.entry_price,
             signal.direction,
             slippage=slippage,
             base_rate=base_rate,
         )
         ```
    3. Update `main()` in `backtest_strategies.py`:
       - Add CLI arguments:
         ```python
         parser.add_argument("--slippage", type=float, default=0.0,
                             help="Slippage penalty in price units (default: 0.0)")
         parser.add_argument("--fee-base-rate", type=float, default=0.063,
                             help="Polymarket dynamic fee base rate (default: 0.063)")
         ```
       - Pass `args.slippage` and `args.fee_base_rate` to `run_strategy()` calls
    4. Handle backward compatibility:
       - If any old analysis code (in `analysis/backtest/module_*.py`) calls `make_trade()` with `fee_rate`, they will get a TypeError
       - Document in a comment at `make_trade()` that old code should replace `fee_rate=X` with `base_rate=X*0.0317` to approximate the same flat fee
       - This is acceptable — M003 is replacing old strategies anyway; the old modules are disposable
  - Verify:
    1. Run verification commands from the slice Verification section above (formula test, slippage diff, CLI flags test)
    2. Confirm all pass
  - Done when:
    - `make_trade()` accepts `slippage` and `base_rate`, adjusts entry price before PnL calculation
    - CLI flags `--slippage` and `--fee-base-rate` exist and are passed through to engine
    - Running with different slippage values produces different PnL
    - Formula verification script passes

## Files Likely Touched

- `src/analysis/backtest/engine.py`
- `src/analysis/backtest_strategies.py`
