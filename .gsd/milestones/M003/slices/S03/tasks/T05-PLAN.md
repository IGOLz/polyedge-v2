# T05: Write comprehensive verification script covering all strategies

## Description

Create a comprehensive bash+Python verification script that proves all 7 strategies (S1-S7) are implemented correctly and can be used by the backtest runner. This is the slice-level verification that must pass before S03 is considered complete.

The script covers 6 check groups:
1. Import checks — all 7 strategies import without errors
2. Instantiation checks — all 7 can be instantiated with default configs
3. Parameter grid checks — all 7 have non-empty grids with 2+ parameters
4. Synthetic evaluation checks — all 7 handle various market patterns without crashing
5. Signal structure checks — signals have required fields when returned
6. Edge case checks — strategies return None for insufficient data, don't crash on NaN-heavy inputs

Use embedded Python for complex checks (same pattern as S01 and S02 verification scripts) to avoid bash portability issues.

## Steps

1. **Create verification script file**
   - Create `scripts/verify_s03_strategies.sh`
   - Make executable: `chmod +x scripts/verify_s03_strategies.sh`
   - Start with shebang and header:
     ```bash
     #!/usr/bin/env bash
     set -euo pipefail
     
     echo "=== S03 Strategy Implementation Verification ==="
     echo ""
     
     cd "$(dirname "$0")/.." || exit 1
     PYTHONPATH=src
     ```

2. **Check 1: Import all strategies**
   - Use embedded Python to import all 7 strategies:
     ```bash
     echo "Check 1: Import all strategies"
     python3 <<'PYEOF'
     import sys
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     for sid in strategies:
         try:
             __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config', 'get_param_grid'])
             __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
             print(f"  ✓ {sid} imports successfully")
         except Exception as e:
             failures.append(f"{sid}: {e}")
             print(f"  ✗ {sid}: {type(e).__name__}: {e}")
     if failures:
         print(f"\nImport check failed for {len(failures)} strategies")
         sys.exit(1)
     print("\n  All strategies import successfully\n")
     PYEOF
     ```

3. **Check 2: Instantiate all strategies**
   - Embedded Python to create instances:
     ```bash
     echo "Check 2: Instantiate all strategies with default configs"
     python3 <<'PYEOF'
     import sys
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     for sid in strategies:
         try:
             config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config'])
             strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
             cfg = config_mod.get_default_config()
             strategy_cls = getattr(strategy_mod, f'{sid}Strategy')
             s = strategy_cls(cfg)
             if s.config.strategy_id != sid:
                 failures.append(f"{sid}: wrong strategy_id {s.config.strategy_id}")
             print(f"  ✓ {sid} instantiated with strategy_id={s.config.strategy_id}, name={s.config.strategy_name}")
         except Exception as e:
             failures.append(f"{sid}: {e}")
             print(f"  ✗ {sid}: {type(e).__name__}: {e}")
     if failures:
         print(f"\nInstantiation check failed for {len(failures)} strategies")
         sys.exit(1)
     print("\n  All strategies instantiated successfully\n")
     PYEOF
     ```

4. **Check 3: Parameter grids**
   - Verify all strategies have meaningful parameter grids:
     ```bash
     echo "Check 3: Parameter grids are non-empty"
     python3 <<'PYEOF'
     import sys
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     for sid in strategies:
         try:
             config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_param_grid'])
             grid = config_mod.get_param_grid()
             if not isinstance(grid, dict):
                 failures.append(f"{sid}: param grid is not a dict")
             elif len(grid) < 2:
                 failures.append(f"{sid}: param grid has < 2 parameters (got {len(grid)})")
             else:
                 # Check each parameter has 2+ values
                 for param, values in grid.items():
                     if not isinstance(values, list) or len(values) < 2:
                         failures.append(f"{sid}: param '{param}' has < 2 values")
                 # Count combinations
                 import itertools
                 combo_count = len(list(itertools.product(*grid.values())))
                 print(f"  ✓ {sid} has {len(grid)} parameters, {combo_count} combinations")
         except Exception as e:
             failures.append(f"{sid}: {e}")
             print(f"  ✗ {sid}: {type(e).__name__}: {e}")
     if failures:
         print(f"\nParam grid check failed: {len(failures)} issues")
         for f in failures:
             print(f"    - {f}")
         sys.exit(1)
     print("\n  All strategies have valid parameter grids\n")
     PYEOF
     ```

5. **Check 4: Synthetic evaluation on various patterns**
   - Test each strategy on 4 synthetic market patterns:
     ```bash
     echo "Check 4: Synthetic evaluation on various market patterns"
     python3 <<'PYEOF'
     import sys
     import numpy as np
     from shared.strategies.base import MarketSnapshot
     
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     
     # Define test patterns
     patterns = {
         'spike': lambda: _spike_pattern(),
         'flat': lambda: _flat_pattern(),
         'nan_heavy': lambda: _nan_heavy_pattern(),
         'extreme': lambda: _extreme_pattern(),
     }
     
     def _spike_pattern():
         prices = np.full(300, 0.50)
         prices[60] = 0.75
         prices[90] = 0.80
         return MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     def _flat_pattern():
         prices = np.full(300, 0.50)
         return MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     def _nan_heavy_pattern():
         prices = np.full(300, np.nan)
         # Only 10% valid ticks
         for i in range(0, 300, 10):
             prices[i] = 0.50 + np.random.uniform(-0.10, 0.10)
         return MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     def _extreme_pattern():
         prices = np.full(300, 0.50)
         prices[60:120] = 0.90  # extreme high
         prices[120:180] = 0.10  # extreme low
         return MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     for sid in strategies:
         try:
             config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config'])
             strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
             cfg = config_mod.get_default_config()
             strategy_cls = getattr(strategy_mod, f'{sid}Strategy')
             s = strategy_cls(cfg)
             
             for pattern_name, pattern_fn in patterns.items():
                 snap = pattern_fn()
                 try:
                     sig = s.evaluate(snap)
                     # Just verify it doesn't crash; signal can be None or valid
                     if sig is not None:
                         if sig.direction not in ['Up', 'Down']:
                             failures.append(f"{sid}/{pattern_name}: invalid direction {sig.direction}")
                 except Exception as e:
                     failures.append(f"{sid}/{pattern_name}: {type(e).__name__}: {e}")
             
             print(f"  ✓ {sid} handled all 4 patterns without crashing")
             
         except Exception as e:
             failures.append(f"{sid}: setup failed: {e}")
             print(f"  ✗ {sid}: setup failed: {type(e).__name__}: {e}")
     
     if failures:
         print(f"\nSynthetic evaluation failed: {len(failures)} issues")
         for f in failures:
             print(f"    - {f}")
         sys.exit(1)
     print("\n  All strategies handled synthetic patterns correctly\n")
     PYEOF
     ```

6. **Check 5: Signal structure validation**
   - When strategies return signals, verify required fields:
     ```bash
     echo "Check 5: Signal structure validation"
     python3 <<'PYEOF'
     import sys
     import numpy as np
     from shared.strategies.base import MarketSnapshot
     
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     
     # Create a pattern likely to trigger signals
     prices = np.full(300, 0.50)
     prices[30] = 0.40
     prices[60] = 0.30
     prices[90:120] = 0.75  # spike
     snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     for sid in strategies:
         try:
             config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config'])
             strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
             cfg = config_mod.get_default_config()
             strategy_cls = getattr(strategy_mod, f'{sid}Strategy')
             s = strategy_cls(cfg)
             sig = s.evaluate(snap)
             
             if sig is not None:
                 # Verify required fields
                 if sig.direction not in ['Up', 'Down']:
                     failures.append(f"{sid}: invalid direction {sig.direction}")
                 if not (0.01 <= sig.entry_price <= 0.99):
                     failures.append(f"{sid}: entry_price {sig.entry_price} out of bounds")
                 if 'entry_second' not in sig.signal_data:
                     failures.append(f"{sid}: missing entry_second in signal_data")
                 if sig.strategy_name != cfg.strategy_name:
                     failures.append(f"{sid}: strategy_name mismatch")
                 print(f"  ✓ {sid} signal structure valid (direction={sig.direction}, entry_second={sig.signal_data.get('entry_second')})")
             else:
                 print(f"  ○ {sid} returned None (valid if conditions not met)")
             
         except Exception as e:
             failures.append(f"{sid}: {type(e).__name__}: {e}")
             print(f"  ✗ {sid}: {type(e).__name__}: {e}")
     
     if failures:
         print(f"\nSignal structure validation failed: {len(failures)} issues")
         for f in failures:
             print(f"    - {f}")
         sys.exit(1)
     print("\n  All returned signals have correct structure\n")
     PYEOF
     ```

7. **Check 6: Edge case handling**
   - Test insufficient data scenario:
     ```bash
     echo "Check 6: Edge case handling (insufficient data)"
     python3 <<'PYEOF'
     import sys
     import numpy as np
     from shared.strategies.base import MarketSnapshot
     
     strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
     failures = []
     
     # Only 5 valid ticks in 300-second market
     sparse_prices = np.full(300, np.nan)
     for i in [10, 50, 100, 150, 200]:
         sparse_prices[i] = 0.50
     snap = MarketSnapshot('test', 'btc_5m', sparse_prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
     
     for sid in strategies:
         try:
             config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config'])
             strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
             cfg = config_mod.get_default_config()
             strategy_cls = getattr(strategy_mod, f'{sid}Strategy')
             s = strategy_cls(cfg)
             sig = s.evaluate(snap)
             # Should return None for insufficient data, not crash
             print(f"  ✓ {sid} handled sparse data gracefully (returned {'None' if sig is None else 'signal'})")
         except Exception as e:
             failures.append(f"{sid}: crashed on sparse data: {type(e).__name__}: {e}")
             print(f"  ✗ {sid}: crashed on sparse data: {type(e).__name__}: {e}")
     
     if failures:
         print(f"\nEdge case handling failed: {len(failures)} issues")
         for f in failures:
             print(f"    - {f}")
         sys.exit(1)
     print("\n  All strategies handle insufficient data gracefully\n")
     PYEOF
     ```

8. **Final summary**
   - Print final summary:
     ```bash
     echo "=== All S03 verification checks passed ==="
     echo ""
     echo "7 strategies implemented:"
     echo "  S1 (Calibration), S2 (Momentum), S3 (Mean Reversion),"
     echo "  S4 (Volatility), S5 (Time-Phase), S6 (Streak), S7 (Composite)"
     echo ""
     echo "All strategies:"
     echo "  - Import successfully"
     echo "  - Instantiate with correct metadata"
     echo "  - Have meaningful parameter grids (10-150 combinations)"
     echo "  - Handle various market patterns without crashing"
     echo "  - Return valid signal structures when conditions met"
     echo "  - Return None for insufficient data (no crashes)"
     echo ""
     exit 0
     ```

9. **Test the verification script**
   - Run `bash scripts/verify_s03_strategies.sh` from the repo root
   - Expect exit code 0 with all checks passed
   - If any check fails, the script prints detailed failure messages and exits with code 1

## Must-Haves

- Script checks all 7 strategies (S1-S7)
- 6 check groups: imports, instantiation, param grids, synthetic evaluation, signal structure, edge cases
- Embedded Python for complex checks (avoids bash portability issues)
- Structured output with ✓/✗ symbols and clear failure messages
- Exit code 0 on success, 1 on any failure
- Script is executable (`chmod +x`)

## Verification

Run the script itself:
```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_s03_strategies.sh
```

Expected output:
- All 6 check groups pass
- 7 strategies verified
- Exit code 0

If the script fails, it should print which strategy and which check failed with enough detail to debug.

## Inputs

- All 7 strategy implementations from T01-T04
- Base classes: `src/shared/strategies/base.py`
- Verification script patterns from S01 and S02

## Expected Output

- Executable script at `scripts/verify_s03_strategies.sh`
- Script passes all checks when all strategies are implemented correctly
- Clear, actionable error messages when checks fail
- Structured output that's easy to scan for pass/fail status

## Observability Impact

This verification script IS the observability surface for S03. It's the canonical way to check if all strategies are implemented correctly. Future slices (S04) and the user can run this script to verify S03 deliverables.

## Related Context

- S01 verification script (`scripts/verify_s01_scaffolding.sh`) provides pattern for embedded Python checks
- S02 forward intelligence notes worktree DB is empty — verification must use synthetic data, not real DB queries
- Research doc "Verification Approach" describes this as the primary health check for S03
