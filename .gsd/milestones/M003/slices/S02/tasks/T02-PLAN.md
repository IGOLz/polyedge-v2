# T02: Add slippage modeling and wire CLI parameters

**Estimated duration:** 45 minutes

## Description

Add configurable slippage penalty to `make_trade()` and expose both slippage and dynamic fee base rate as CLI flags in `backtest_strategies.py`. This implements R017 (realistic slippage modeling) and completes the engine upgrade by giving users control over both fee and slippage assumptions.

Slippage models the reality that by the time a strategy's signal is executed, the market price has moved. For Up bets, slippage increases cost (we pay more than detected). For Down bets, slippage decreases the entry price (the Up token got cheaper, making the Down token more expensive — worse for us). The model penalizes entry prices in the unfavorable direction before calculating PnL.

This task wires the dynamic fee function from T01 into the full backtest pipeline and makes both slippage and base rate user-controllable via `--slippage` and `--fee-base-rate` CLI flags.

## Must-Haves

- `make_trade()` accepts `slippage` and `base_rate` parameters
- Slippage adjusts entry price before PnL calculation: Up bets add slippage, Down bets subtract
- Adjusted entry prices clamped to [0.01, 0.99]
- `run_strategy()` accepts and passes slippage/base_rate to `make_trade()`
- CLI accepts `--slippage` and `--fee-base-rate` flags
- Backward compatibility: defaults `slippage=0.0`, `base_rate=0.063`
- Running with different slippage produces different PnL (verified by diff)

## Steps

1. **Update make_trade() signature and slippage logic**
   - Open `src/analysis/backtest/engine.py`
   - Find `def make_trade(market, second_entered, entry_price, direction, second_exited=-1, exit_price=None, fee_rate=DEFAULT_FEE_RATE):`
   - Change signature to:
     ```python
     def make_trade(market, second_entered, entry_price, direction,
                    second_exited=-1, exit_price=None, 
                    slippage=0.0, base_rate=0.063):
     ```
   - Remove the `fee_rate` parameter entirely (breaking change documented below)
   - After extracting `actual = market['final_outcome']`, add slippage adjustment:
     ```python
     # Apply slippage penalty (unfavorable direction)
     adjusted_entry = entry_price
     if slippage != 0.0:
         if direction == "Up":
             adjusted_entry = entry_price + slippage
         else:  # Down
             adjusted_entry = entry_price - slippage
         # Clamp to valid token price range
         adjusted_entry = max(0.01, min(0.99, adjusted_entry))
     ```
   - Update the PnL calculation branches:
     - For exit case: `pnl = calculate_pnl_exit(adjusted_entry, exit_price, base_rate)`
     - For hold case: `pnl = calculate_pnl_hold(adjusted_entry, direction, actual, base_rate)`
   - Store the **original** `entry_price` in the Trade object (not adjusted), so reports show what the strategy detected
   - Add a docstring note:
     ```python
     """Create a Trade object with PnL calculated.
     
     Args:
         slippage: Entry price penalty (default 0.0). Added to Up bets, subtracted from Down.
         base_rate: Polymarket dynamic fee base rate (default 0.063).
     
     Note: Removed fee_rate parameter. Old code using fee_rate should pass base_rate instead.
           To approximate flat 2% fee, use base_rate ≈ 0.0317 (produces ~2% at extreme prices).
     """
     ```

2. **Update run_strategy() to accept and pass parameters**
   - Open `src/analysis/backtest_strategies.py`
   - Find `def run_strategy(strategy_id: str, strategy, markets: list[dict]):`
   - Change signature to:
     ```python
     def run_strategy(
         strategy_id: str,
         strategy,
         markets: list[dict],
         slippage: float = 0.0,
         base_rate: float = 0.063,
     ) -> tuple[list[Trade], dict]:
     ```
   - Find the `make_trade()` call inside the loop (around line 62)
   - Update to pass new parameters:
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

3. **Add CLI arguments and wire through main()**
   - In `backtest_strategies.py`, find `def main()` and the argument parser setup
   - After existing arguments, add:
     ```python
     parser.add_argument(
         "--slippage",
         type=float,
         default=0.0,
         help="Slippage penalty in price units (default: 0.0). "
              "Models execution lag — Up bets pay more, Down bets worse fill.",
     )
     parser.add_argument(
         "--fee-base-rate",
         type=float,
         default=0.063,
         help="Polymarket dynamic fee base rate (default: 0.063). "
              "Produces ~3.15%% peak fee at 50/50 prices.",
     )
     ```
   - Find the `run_strategy()` calls in the main loop (around line 105)
   - Update both calls (single-strategy and all-strategies paths):
     ```python
     trades, metrics = run_strategy(
         sid, strat, markets, 
         slippage=args.slippage, 
         base_rate=args.fee_base_rate
     )
     ```

4. **Test slippage impact**
   - Run the same strategy with zero slippage:
     ```bash
     cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies \
       --strategy S1 --slippage 0.0 > /tmp/no_slippage.txt 2>&1
     ```
   - Run with 1-cent slippage:
     ```bash
     cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies \
       --strategy S1 --slippage 0.01 > /tmp/with_slippage.txt 2>&1
     ```
   - Compare outputs (PnL should differ):
     ```bash
     diff -u /tmp/no_slippage.txt /tmp/with_slippage.txt | grep -E '(total_pnl|PnL=)'
     ```
   - If PnL values differ, slippage is working
   - If no difference or error: check that S1 strategy exists and produces trades

5. **Test CLI flag acceptance**
   - Run with both flags to confirm no errors:
     ```bash
     cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies \
       --strategy S1 --slippage 0.01 --fee-base-rate 0.05
     ```
   - Exit code 0 = success

## Verification

**Automated slippage test:**
```bash
cd src

# Zero slippage run
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.0 > /tmp/no_slippage.txt 2>&1

# 1-cent slippage run
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.01 > /tmp/with_slippage.txt 2>&1

# Verify PnL differs
if diff -u /tmp/no_slippage.txt /tmp/with_slippage.txt | grep -E '(total_pnl|PnL=)' > /dev/null; then
  echo "✓ Slippage changes PnL as expected"
else
  echo "✗ Slippage did not affect PnL (or strategy produced no trades)"
fi
```

**CLI flag acceptance test:**
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --strategy S1 --slippage 0.01 --fee-base-rate 0.05 > /dev/null 2>&1 \
  && echo "✓ CLI flags accepted" \
  || echo "✗ CLI flags caused error"
```

**Manual inspection:**
- Open `src/analysis/backtest/engine.py`
  - Confirm `make_trade()` has `slippage` and `base_rate` parameters
  - Confirm slippage adjustment code exists (Up: +slippage, Down: -slippage)
  - Confirm adjusted_entry is clamped to [0.01, 0.99]
  - Confirm PnL functions receive `adjusted_entry` and `base_rate`
- Open `src/analysis/backtest_strategies.py`
  - Confirm `run_strategy()` has `slippage` and `base_rate` parameters
  - Confirm `make_trade()` call passes them
  - Confirm `--slippage` and `--fee-base-rate` CLI arguments exist
  - Confirm `main()` passes `args.slippage` and `args.fee_base_rate` to `run_strategy()`

## Inputs

- T01 output: `polymarket_dynamic_fee()` function and updated PnL functions using `base_rate`
- Current `make_trade()` with `fee_rate` parameter
- Current `backtest_strategies.py` CLI with no slippage/base_rate flags
- Research guidance on slippage direction (Up: +slippage, Down: -slippage)

## Expected Output

- `make_trade()` signature changed to accept `slippage` and `base_rate`
- Slippage adjustment code present, clamping to [0.01, 0.99]
- `run_strategy()` signature changed, parameters passed to `make_trade()`
- CLI has `--slippage` and `--fee-base-rate` arguments
- Running with different slippage values produces different PnL
- All verification commands pass

## Observability Impact

**Low impact** — adds two new configuration parameters but no new runtime state or failure modes.

- **Runtime signals:** None added. The slippage and base_rate parameters affect PnL calculation but don't produce logs or events.
- **Inspection surfaces:** Trade objects already contain `entry_price` and `pnl`. The `entry_price` field will show the **original** detected price (not adjusted), so there's no direct way to see slippage from a Trade object alone. This is intentional — slippage is a backtest parameter, not per-trade metadata. Users inspect slippage impact by comparing backtest runs with different `--slippage` values.
- **Failure visibility:** If slippage adjustment breaks (e.g., incorrect direction), PnL will be systematically wrong. The verification diff test catches this by comparing zero vs non-zero slippage runs. If the diff shows no change, slippage isn't working.
- **Redaction constraints:** None — slippage and base_rate are public configuration values.

**Backward compatibility concern:** Removing `fee_rate` parameter from `make_trade()` is a breaking change. Any code calling `make_trade(fee_rate=...)` will get a TypeError. Mitigation: Document in the function docstring how to migrate (replace `fee_rate` with equivalent `base_rate`). This is acceptable because M003 replaces old strategies anyway — the old analysis modules (`module_*.py`) are disposable. If needed, future cleanup can update those modules or delete them.

## Related Skills

None — this is pure Python parameter wiring with no external dependencies.
