# T02: Write and run verification script

## Description

Write `src/scripts/verify_m004_s01.py` that proves S01 is complete: all 7 strategies have `stop_loss` and `take_profit` keys in their parameter grids, values are non-empty lists, and grid sizes are manageable (<1000 combinations per strategy).

The script imports each strategy config, calls `get_param_grid()`, checks for required keys, and computes the Cartesian product size to confirm parameter space explosion is under control.

## Steps

1. **Create verification script:** `src/scripts/verify_m004_s01.py`

2. **Script structure:**
   ```python
   #!/usr/bin/env python3
   """Verify S01: Parameter Grid Foundation — all strategies have SL/TP in param grids."""
   
   import sys
   from itertools import product
   
   def verify_strategy(strategy_id):
       """Import strategy config, check for SL/TP keys, compute grid size."""
       module_name = f"shared.strategies.{strategy_id}.config"
       try:
           mod = __import__(module_name, fromlist=["get_param_grid"])
           get_param_grid = mod.get_param_grid
       except ImportError as e:
           print(f"  [FAIL] {strategy_id} import failed: {e}")
           return False
       
       grid = get_param_grid()
       
       # Check for stop_loss key
       if "stop_loss" not in grid:
           print(f"  [FAIL] {strategy_id} missing 'stop_loss' key")
           return False
       print(f"  [PASS] {strategy_id} has stop_loss key")
       
       # Check for take_profit key
       if "take_profit" not in grid:
           print(f"  [FAIL] {strategy_id} missing 'take_profit' key")
           return False
       print(f"  [PASS] {strategy_id} has take_profit key")
       
       # Check non-empty
       if not grid["stop_loss"]:
           print(f"  [FAIL] {strategy_id} stop_loss is empty")
           return False
       print(f"  [PASS] {strategy_id} stop_loss has {len(grid['stop_loss'])} values")
       
       if not grid["take_profit"]:
           print(f"  [FAIL] {strategy_id} take_profit is empty")
           return False
       print(f"  [PASS] {strategy_id} take_profit has {len(grid['take_profit'])} values")
       
       # Compute grid size
       grid_size = 1
       for key, values in grid.items():
           grid_size *= len(values)
       
       print(f"  Grid size: {grid_size} combinations")
       if grid_size > 1000:
           print(f"  [WARN] Grid size exceeds 1000 — may be slow")
       
       return True
   
   def main():
       print("=== S01 Verification: Parameter Grid Foundation ===\n")
       
       strategies = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
       all_passed = True
       
       for sid in strategies:
           print(f"{sid} config:")
           if not verify_strategy(sid):
               all_passed = False
           print()
       
       # Check TEMPLATE
       print("TEMPLATE config:")
       if not verify_strategy("TEMPLATE"):
           all_passed = False
       print()
       
       if all_passed:
           print("✓ All checks passed. S01 complete.")
           sys.exit(0)
       else:
           print("✗ Some checks failed.")
           sys.exit(1)
   
   if __name__ == "__main__":
       main()
   ```

3. **Make executable:** `chmod +x src/scripts/verify_m004_s01.py`

4. **Run verification:** `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py`

5. **Verify output:**
   - All strategies print `[PASS]` for SL/TP key checks
   - Grid sizes printed and all <1000
   - Final line: "✓ All checks passed. S01 complete."

## Must-Haves

- Script imports all S1-S7 and TEMPLATE configs
- Checks for presence of 'stop_loss' and 'take_profit' keys
- Verifies keys map to non-empty lists
- Computes and prints grid sizes (Cartesian product of all param values)
- Returns exit code 0 on success, 1 on any failure
- Clear PASS/FAIL output per strategy

## Verification

```bash
cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py
```

Expected output format:
```
=== S01 Verification: Parameter Grid Foundation ===

S1 config:
  [PASS] S1 has stop_loss key
  [PASS] S1 has take_profit key
  [PASS] S1 stop_loss has 3 values
  [PASS] S1 take_profit has 3 values
  Grid size: 972 combinations

S2 config:
  [PASS] S2 has stop_loss key
  ...

✓ All checks passed. S01 complete.
```

Exit code: 0

## Inputs

From T01:
- `src/shared/strategies/S1-S7/config.py` — updated with SL/TP keys
- `src/shared/strategies/TEMPLATE/config.py` — updated with example SL/TP

## Expected Output

- File created: `src/scripts/verify_m004_s01.py`
- Script runs successfully
- All strategies pass SL/TP checks
- Grid sizes printed and confirmed <1000
- Exit code 0

## Observability Impact

**New Signals:**
- `src/scripts/verify_m004_s01.py` becomes the authoritative verification tool for S01 completion — future agents can run it to confirm SL/TP parameter grid structure
- Script exit code (0=pass, 1=fail) provides binary health signal for CI or manual verification
- Per-strategy grid size printed to stdout reveals parameter space explosion risk before grid search runs

**Inspection Surface:**
- Run: `cd src && PYTHONPATH=. python3 scripts/verify_m004_s01.py` to check all 8 configs (S1-S7 + TEMPLATE)
- Output shows: key presence (stop_loss, take_profit), value counts, and total grid size per strategy
- Failure output identifies exact strategy and missing/invalid key

**Failure Visibility:**
- Missing config file: Python import error with traceback showing file path
- Missing SL/TP keys: `[FAIL] {strategy} missing '{key}'` message to stdout, exit 1
- Empty parameter lists: `[FAIL] {strategy} {key} is empty` message to stdout, exit 1
- Grid explosion: `[WARN] Grid size exceeds 1000` warning (non-fatal) for strategies with large parameter spaces

**Future Use:**
- S02 and S03 tasks can assume this script exists and run it as a precondition check
- CI pipelines can add this script to verify strategy config integrity
- When adding new strategies, run this script to confirm they follow the SL/TP parameter convention
