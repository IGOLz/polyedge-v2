# T01: Implement dynamic fee formula and update PnL calculations

**Estimated duration:** 45 minutes

## Description

Add the Polymarket dynamic fee formula (`baseRate × min(price, 1-price)`) as a new function in `engine.py` and update both PnL calculation functions to use it instead of the flat `fee_rate` parameter. This implements R016 (dynamic fees for realistic backtest profitability).

The dynamic fee model reflects Polymarket's actual CLOB fee structure for short-term crypto markets: fees peak at ~3.15% near 50/50 (toss-up) prices and drop to ~0.63% for confident outcomes (10-cent or 90-cent tokens). The current flat 2% understates costs for balanced markets and overstates for lopsided ones.

**Key constraint:** Fee calculation must use the entry price (the price we paid for the token), not the exit price. Polymarket charges fees when you buy, not when you resolve.

## Must-Haves

- `polymarket_dynamic_fee(price, base_rate)` function returns `base_rate × min(price, 1 - price)`
- `calculate_pnl_hold()` calls `polymarket_dynamic_fee(entry_price, base_rate)` instead of `fee_rate × gross`
- `calculate_pnl_exit()` calls `polymarket_dynamic_fee(entry_price, base_rate)` instead of `fee_rate × max(0, gross)`
- Both PnL functions change signature from `fee_rate=DEFAULT_FEE_RATE` to `base_rate=0.063`
- Formula verification passes: fee at 0.50 = 0.0315, fee at 0.10 = 0.0063, fee at 0.90 = 0.0063

## Steps

1. **Add dynamic fee function to engine.py**
   - Open `src/analysis/backtest/engine.py`
   - After imports and before the `Trade` dataclass (around line 10), add:
     ```python
     def polymarket_dynamic_fee(price: float, base_rate: float = 0.063) -> float:
         """Calculate Polymarket dynamic taker fee.
         
         Formula: base_rate × min(price, 1 - price)
         
         Fees peak at ~3.15% for 50-cent tokens (balanced markets) and drop to
         ~0.63% for extreme prices (confident outcomes). Base rate of 0.063
         produces the observed peak fee.
         
         Args:
             price: Token price (0.0 to 1.0)
             base_rate: Fee base rate (default 0.063)
         
         Returns:
             Fee as a decimal (e.g., 0.0315 for 3.15%)
         """
         price = max(0.0, min(1.0, price))  # clamp to valid range
         return base_rate * min(price, 1.0 - price)
     ```

2. **Update calculate_pnl_hold()**
   - Find the function signature (currently `def calculate_pnl_hold(entry_price, direction, actual_result, fee_rate=DEFAULT_FEE_RATE):`)
   - Change to: `def calculate_pnl_hold(entry_price, direction, actual_result, base_rate=0.063):`
   - Find the line `return gross - fee_rate * gross` (in the win branch)
   - Change to: `return gross - polymarket_dynamic_fee(entry_price, base_rate) * gross`
   - The loss branch (`return -entry_price`) stays unchanged — no fee refund on losses

3. **Update calculate_pnl_exit()**
   - Find the function signature (currently `def calculate_pnl_exit(entry_price, exit_price, fee_rate=DEFAULT_FEE_RATE):`)
   - Change to: `def calculate_pnl_exit(entry_price, exit_price, base_rate=0.063):`
   - Find the line `fee = fee_rate * max(0.0, gross)`
   - Change to: `fee = polymarket_dynamic_fee(entry_price, base_rate) * max(0.0, gross)`

4. **Verify formula correctness**
   - From `src/`, run in a Python REPL:
     ```python
     from analysis.backtest.engine import polymarket_dynamic_fee
     
     fee_50 = polymarket_dynamic_fee(0.50, 0.063)
     fee_10 = polymarket_dynamic_fee(0.10, 0.063)
     fee_90 = polymarket_dynamic_fee(0.90, 0.063)
     
     print(f"Fee at 0.50: {fee_50:.4f} (expect 0.0315)")
     print(f"Fee at 0.10: {fee_10:.4f} (expect 0.0063)")
     print(f"Fee at 0.90: {fee_90:.4f} (expect 0.0063)")
     
     assert abs(fee_50 - 0.0315) < 0.0001, f"Expected 0.0315, got {fee_50}"
     assert abs(fee_10 - 0.0063) < 0.0001, f"Expected 0.0063, got {fee_10}"
     assert abs(fee_90 - 0.0063) < 0.0001, f"Expected 0.0063, got {fee_90}"
     
     print("✓ All fee calculations verified")
     ```
   - All assertions must pass

## Verification

**Automated:**
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

**Exit code 0 = pass, non-zero = fail**

**Manual inspection:**
- Open `src/analysis/backtest/engine.py`
- Confirm `polymarket_dynamic_fee()` exists and has the correct formula
- Confirm `calculate_pnl_hold()` calls it with `entry_price`
- Confirm `calculate_pnl_exit()` calls it with `entry_price`
- Both functions use `base_rate` parameter, not `fee_rate`

## Inputs

- Current `engine.py` with flat `DEFAULT_FEE_RATE = 0.02` and `fee_rate` parameters
- Research doc formula: `baseRate × min(price, 1-price)`
- Expected peak fee: 3.15% at price=0.50 with base_rate=0.063

## Expected Output

- `polymarket_dynamic_fee()` function exists in `engine.py`
- `calculate_pnl_hold()` signature changed to use `base_rate`
- `calculate_pnl_exit()` signature changed to use `base_rate`
- Formula verification script passes with all assertions

## Observability Impact

**None** — this task only changes internal calculation logic. No new runtime signals, logs, or inspection surfaces. The impact is purely mathematical: backtest PnL will be different (more accurate) but the change won't be observable until T02 wires it into the CLI and strategies run with the new logic.

The `Trade` dataclass already captures `pnl` — that field will reflect dynamic fees after this change, but there's no way to tell from a Trade object alone whether dynamic or flat fees were used. That's intentional — the fee model is a global engine setting, not per-trade metadata.

## Related Skills

None — this is pure Python math implementation with no external dependencies.
