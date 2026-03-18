# T01: Fix Market Dict Key Mismatch & Verify SL/TP Simulation

## Description

The backtest engine's `make_trade()` function looks for `market.get('prices')` to run SL/TP simulation (line 198 in engine.py), but the data loader returns market dicts with a `'ticks'` key instead. This mismatch causes the SL/TP simulator to be skipped, and all trades default to `exit_reason='resolution'` even when stop_loss and take_profit parameters are correctly passed through the pipeline.

This task fixes the architectural mismatch by renaming the key from `'ticks'` to `'prices'` in two places:
1. The data loader's market dict construction (data_loader.py line 117)
2. The backtest_strategies.py consumption of that dict (line 68)

These changes must be atomic (same commit) to avoid breaking the backtest_strategies module.

## Steps

1. **Verify the current key mismatch:**
   ```bash
   cd src
   rg "market\['ticks'\]" analysis/
   rg "market.get\('prices'\)" analysis/
   ```
   Expected: backtest_strategies.py uses `market["ticks"]`, engine.py checks `market.get('prices')`.

2. **Fix data_loader.py line 117:**
   - Open `src/analysis/backtest/data_loader.py`
   - Find line 117: `'ticks': tick_array`
   - Change to: `'prices': tick_array`
   - The market dict should now return `{'market_id': ..., 'title': ..., 'prices': tick_array, ...}` instead of `'ticks': tick_array`

3. **Fix backtest_strategies.py line 68:**
   - Open `src/analysis/backtest_strategies.py`
   - Find line 68: `prices=market["ticks"]`
   - Change to: `prices=market["prices"]`
   - This updates the `market_to_snapshot()` function to match the renamed key

4. **Verify no other references to market['ticks'] exist:**
   ```bash
   cd src
   rg "market\['ticks'\]" .
   ```
   Expected: No matches (we just fixed the only two references).

5. **Run verification to prove SL/TP simulation works:**
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.backtest_strategies import run_strategy
   from analysis.backtest import data_loader
   from shared.strategies import get_strategy
   from collections import Counter
   
   markets = data_loader.load_all_data()
   strategy = get_strategy('S1')
   trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.4, take_profit=0.7)
   
   exit_reasons = Counter(t.exit_reason for t in trades)
   print('Exit reason counts:', exit_reasons)
   assert 'sl' in exit_reasons, 'Expected at least one stop loss exit'
   assert 'tp' in exit_reasons, 'Expected at least one take profit exit'
   assert 'resolution' in exit_reasons, 'Expected at least one resolution exit'
   print('✓ Exit reason diversity verified')
   "
   ```
   Expected output: Counter showing mix of 'sl', 'tp', and 'resolution' values; all assertions pass.

6. **Commit the fix:**
   ```bash
   git add src/analysis/backtest/data_loader.py src/analysis/backtest_strategies.py
   git commit -m "fix(M004-S04-T01): rename market dict key from 'ticks' to 'prices' to unblock SL/TP simulation

   The engine expects market.get('prices') but data loader returned 'ticks',
   causing SL/TP simulator to be skipped. This atomic change renames the key
   in both the producer (data_loader.py) and consumer (backtest_strategies.py)
   to maintain consistency and enable early exit simulation."
   ```

## Must-Haves

- Market dict key renamed from `'ticks'` to `'prices'` in data_loader.py line 117
- backtest_strategies.py line 68 updated to access `market["prices"]` instead of `market["ticks"]`
- Both changes committed atomically to avoid breaking the pipeline
- Verification proves exit_reason shows at least one 'sl', one 'tp', and some 'resolution' values

## Verification

Run the verification command from step 5 above. Success criteria:
- Counter shows exit_reason distribution with all three values ('sl', 'tp', 'resolution')
- At least one trade has exit_reason='sl'
- At least one trade has exit_reason='tp'
- At least one trade has exit_reason='resolution'
- All assertions pass without errors

## Inputs

- Existing market dicts from data_loader with `'ticks'` key (architectural mismatch)
- S02's `simulate_sl_tp_exit()` function in engine.py expecting `market.get('prices')`
- S03's parameter threading delivering stop_loss and take_profit to make_trade()

## Expected Output

- data_loader.py returns market dicts with `'prices': tick_array` instead of `'ticks': tick_array`
- backtest_strategies.py reads `market["prices"]` without KeyError
- Engine's `market.get('prices')` check succeeds on line 198, enabling SL/TP simulation (lines 199-206)
- Trade objects have exit_reason values of 'sl', 'tp', or 'resolution' reflecting actual price movements
- Verification command output showing Counter with mix of exit reasons and all assertions passing

## Observability Impact

**Signals changed:**
- Trade.exit_reason now reflects actual SL/TP simulation results ('sl', 'tp') instead of always 'resolution'
- Market dict structure changed from `{'ticks': tick_array}` to `{'prices': tick_array}`

**Inspection method:**
- Run verification command from step 5 to see Counter of exit reasons
- Import and inspect market dict keys: `data_loader.load_all_data()[0].keys()` → should include 'prices', not 'ticks'
- Check Trade objects: `trades[0].exit_reason` → should show 'sl', 'tp', or 'resolution' based on price movements

**Failure states now visible:**
- If SL/TP simulation still doesn't run: verification Counter shows only 'resolution' values
- If key mismatch persists: KeyError when accessing market['prices'] in engine.py or market['ticks'] in backtest_strategies.py
- If only partial fix applied: one module errors while the other works (atomic commit prevents this)
