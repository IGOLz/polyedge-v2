---
id: S01
parent: M003
milestone: M003
written: 2026-03-18T13:58:36+01:00
---

# S01: Clean slate + strategy scaffolding — UAT

**Milestone:** M003
**Written:** 2026-03-18

## UAT Type

- **UAT mode:** artifact-driven
- **Why this mode is sufficient:** S01 delivers scaffolding only (no runtime behavior, no live systems). All deliverables are static artifacts (folders, files, code structure) that can be verified by inspection, registry discovery, and instantiation. No server, no backtest execution, no live trading involved at this stage.

## Preconditions

- Working directory: `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003`
- Python environment active with project dependencies installed
- `src/` folder exists with `shared/strategies/` directory structure

## Smoke Test

Run the verification script:
```bash
bash scripts/verify_s01_scaffolding.sh
```

**Expected:** Script exits 0 with message "S01 scaffolding verification PASSED ✓" and shows 25 passed checks, 0 failed.

If this passes, S01 is fundamentally correct. Proceed to full test cases for detailed inspection.

## Test Cases

### 1. Verify old strategies replaced

1. Run: `ls src/shared/strategies/`
2. **Expected:** Output shows 8 folders: `S1  S2  S3  S4  S5  S6  S7  TEMPLATE`. Old S1/S2 are gone; new S1/S2 exist.
3. Run: `grep "strategy_name" src/shared/strategies/S1/config.py`
4. **Expected:** Output contains `strategy_name="S1_calibration"` (not old spike reversion strategy)
5. Run: `grep "strategy_name" src/shared/strategies/S2/config.py`
6. **Expected:** Output contains `strategy_name="S2_momentum"` (not old volatility strategy)

### 2. Verify TEMPLATE has param grid function

1. Run: `grep -A 10 "def get_param_grid" src/shared/strategies/TEMPLATE/config.py`
2. **Expected:** Shows complete function definition with docstring explaining grid-search usage and example parameter ranges
3. Run: `python3 -c "import sys; sys.path.insert(0, 'src'); from shared.strategies.TEMPLATE.config import get_param_grid; print(get_param_grid())"`
4. **Expected:** Prints empty dict `{}` with no errors (function is callable)
5. Run: `grep "## 6. Add \`get_param_grid()\`" src/shared/strategies/TEMPLATE/README.md`
6. **Expected:** Output shows section 6 title without "(Optional)" — param grid is now required

### 3. Verify all 7 strategy folders exist with correct structure

1. Run: `for i in {1..7}; do echo "=== S$i ===" && ls src/shared/strategies/S$i/; done`
2. **Expected:** Each strategy shows 4 files: `__init__.py  config.py  README.md  strategy.py`
3. Run: `for i in {1..7}; do grep "class S${i}Config" src/shared/strategies/S$i/config.py || echo "S$i FAIL"; done`
4. **Expected:** No output (all grep commands succeed, no "FAIL" printed)
5. Run: `for i in {1..7}; do grep "class S${i}Strategy" src/shared/strategies/S$i/strategy.py || echo "S$i FAIL"; done`
6. **Expected:** No output (all grep commands succeed, no "FAIL" printed)

### 4. Verify registry discovers all 8 strategies

1. Run:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'src')
   from shared.strategies.registry import discover_strategies
   strategies = discover_strategies()
   print(f'Found {len(strategies)} strategies:', sorted(strategies.keys()))
   "
   ```
2. **Expected:** Output shows `Found 8 strategies: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE']`

### 5. Verify each strategy instantiates with correct metadata

1. Run:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'src')
   from shared.strategies.registry import get_strategy
   for sid in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']:
       s = get_strategy(sid)
       print(f'{sid}: {s.config.strategy_id} | {s.config.strategy_name}')
   "
   ```
2. **Expected:** Output shows 7 lines with correct IDs and names:
   ```
   S1: S1 | S1_calibration
   S2: S2 | S2_momentum
   S3: S3 | S3_reversion
   S4: S4 | S4_volatility
   S5: S5 | S5_time_phase
   S6: S6 | S6_streak
   S7: S7 | S7_composite
   ```

### 6. Verify stub behavior: evaluate() returns None

1. Run:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'src')
   from shared.strategies.registry import get_strategy
   from shared.strategies.base import MarketSnapshot
   
   # Create dummy snapshot
   snapshot = MarketSnapshot(
       market_id='test_market',
       asset='BTC',
       prices_by_second={0: {'yes': 0.50, 'no': 0.50}},
       current_second=0
   )
   
   # Test S1 and S3 (spot check)
   s1 = get_strategy('S1')
   s3 = get_strategy('S3')
   
   result1 = s1.evaluate(snapshot)
   result3 = s3.evaluate(snapshot)
   
   print(f'S1 evaluate: {result1}')
   print(f'S3 evaluate: {result3}')
   print(f'Both None: {result1 is None and result3 is None}')
   "
   ```
2. **Expected:**
   ```
   S1 evaluate: None
   S3 evaluate: None
   Both None: True
   ```

### 7. Verify no leftover Template references in code

1. Run: `grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/*.py`
2. **Expected:** No output (grep finds nothing, exit code 1 is expected behavior for "no matches")
3. Run: `echo $?` (check exit code)
4. **Expected:** Exit code is 1 (grep found no matches, which is correct — we want zero Template references)

## Edge Cases

### Empty param grids are valid stubs

1. Run:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'src')
   from shared.strategies.registry import get_strategy
   
   s1 = get_strategy('S1')
   grid = s1.config.get_param_grid()
   
   print(f'S1 param grid: {grid}')
   print(f'Is empty dict: {grid == {}}')
   print(f'Is dict type: {isinstance(grid, dict)}')
   "
   ```
2. **Expected:**
   ```
   S1 param grid: {}
   Is empty dict: True
   Is dict type: True
   ```
3. **Why this is correct:** S01 delivers scaffolding only. Empty param grids are intentional stubs with TODO comments. S03 will populate them with real parameter ranges.

### TEMPLATE is discoverable like any other strategy

1. Run:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'src')
   from shared.strategies.registry import get_strategy
   
   template = get_strategy('TEMPLATE')
   print(f'TEMPLATE strategy_id: {template.config.strategy_id}')
   print(f'TEMPLATE strategy_name: {template.config.strategy_name}')
   "
   ```
2. **Expected:**
   ```
   TEMPLATE strategy_id: TEMPLATE
   TEMPLATE strategy_name: template_strategy
   ```
3. **Why this matters:** TEMPLATE must remain discoverable so developers can inspect the reference implementation. It's not just documentation — it's a working example.

### Strategy folders contain README but content is generic

1. Run: `head -5 src/shared/strategies/S1/README.md`
2. **Expected:** Shows "# Strategy Template" header and generic TEMPLATE documentation
3. **Why this is expected:** S01 focused on code scaffolding. Strategy-specific README updates are deferred to S03 when real logic is implemented and documented.

## Failure Signals

- Verification script exits non-zero — indicates structural failure in scaffolding
- Registry discovers fewer than 8 strategies — missing folder or broken imports
- `get_strategy()` raises ImportError or AttributeError — class naming mismatch or missing files
- Strategy metadata doesn't match naming map — wrong strategy_id or strategy_name
- `evaluate()` returns non-None value — premature implementation (should be stub)
- Template references found in S1-S7 code — incomplete class renaming
- Missing `__init__.py` in any strategy folder — Python won't treat it as a package

## Requirements Proved By This UAT

- **R002** — All 7 strategies live in `shared/strategies/S1/` through `S7/` with config and evaluate modules
- **R008** — Registry discovers strategies by scanning folders; proven by test case 4
- **R011** — TEMPLATE has documented skeleton with param grid function; proven by test case 2
- **R014** — Each strategy is self-contained folder with config, evaluate(), and param grid stub; proven by test cases 3, 5, 6
- **R015** — Old S1/S2 deleted and TEMPLATE updated; proven by test case 1

## Not Proven By This UAT

- **Real strategy implementations** — All evaluate() methods return None. S03 will implement actual logic.
- **Parameter grid ranges** — All get_param_grid() return empty dicts. S03 will define meaningful parameter spaces.
- **Backtest execution** — Strategies aren't runnable yet. S02 (engine upgrades) and S03 (implementations) required first.
- **End-to-end parity** — Can't verify analysis/trading parity without real strategies producing signals.
- **Dynamic fees and slippage** — Engine upgrades are S02's responsibility.
- **Strategy profitability** — No logic to evaluate yet; S03+S04 will address.

## Notes for Tester

- **This is scaffolding only** — Don't expect strategies to do anything useful yet. The goal is structural correctness, not functional behavior.
- **README files are stale** — All strategy folders have generic TEMPLATE documentation. Ignore README content for now; focus on code structure and registry discovery.
- **Empty param grids are expected** — All `get_param_grid()` return `{}` by design. This will be populated in S03.
- **Trust the verification script** — If `scripts/verify_s01_scaffolding.sh` exits 0, S01 is complete. Manual test cases provide deeper inspection but aren't necessary if the script passes.
- **No need to run backtests** — Strategies return None from evaluate(), so backtest would produce zero signals. This is correct stub behavior, not a bug.
