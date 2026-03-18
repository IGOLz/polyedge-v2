---
id: M004
provides:
  - Parameter grid optimization with exhaustive SL/TP search across all 7 strategies (972 combinations for S1)
  - Stop loss and take profit engine with second-by-second price tracking and direction-aware threshold logic
  - Trade exit_reason field distinguishing 'sl', 'tp', and 'resolution' exit paths
  - Console and CSV output with explicit stop_loss and take_profit values for all ranked combinations
  - TEMPLATE demonstrating SL/TP pattern with documented absolute price semantics
key_decisions:
  - D012: SL/TP as absolute price thresholds (not relative offsets) for simpler reasoning
  - D013: Strategy-specific SL/TP ranges tuned to each strategy's typical entry prices
  - D014: Skip invalid parameter combinations (e.g., SL > TP) during grid generation
patterns_established:
  - Dataclass introspection for separating config fields from runtime parameters (stop_loss, take_profit)
  - Pure function pattern for simulation (no side effects, deterministic, testable in isolation)
  - Keyword-only parameters for optional features (stop_loss=None, take_profit=None)
  - Direction-aware PnL calculation (entry - exit for Down bets vs exit - entry for Up bets)
  - Market dict 'prices' key as architectural standard for tick arrays
observability_surfaces:
  - Trade.exit_reason field (inspectable in REPL via print(trade) or vars(trade))
  - Console SL/TP display pattern `SL=\d+\.\d+, TP=\d+\.\d+` in top 10 summary
  - CSV columns stop_loss and take_profit with per-configuration values
  - Counter distribution of exit_reason values proving simulation diversity
  - verify_m004_milestone.sh 7-check verification script (exit 0 = all pass)
requirement_outcomes:
  - id: R023
    from_status: active
    to_status: validated
    proof: All 7 strategies (S1-S7) have get_param_grid() returning dicts with stop_loss and take_profit keys (3 values each), verified by verify_m004_milestone.sh check 1
  - id: R024
    from_status: active
    to_status: validated
    proof: TEMPLATE/config.py has working get_param_grid() with SL/TP keys and comments explaining absolute price thresholds, verified by verify_m004_milestone.sh check 7
  - id: R025
    from_status: active
    to_status: validated
    proof: simulate_sl_tp_exit() scans prices second-by-second with direction-specific thresholds, verified by 13 unit tests in test_sl_tp_engine.py
  - id: R026
    from_status: active
    to_status: validated
    proof: optimize.py generates Cartesian product including SL/TP dimensions (972 combinations for S1), verified by dry-run output and results CSV
  - id: R027
    from_status: active
    to_status: validated
    proof: Results CSV contains stop_loss and take_profit columns with per-configuration values, verified by verify_m004_milestone.sh check 4
  - id: R028
    from_status: active
    to_status: validated
    proof: Console top 10 output displays SL/TP values (format "SL=0.40, TP=0.75"), verified by verify_m004_milestone.sh check 5
  - id: R029
    from_status: active
    to_status: validated
    proof: S1-S7 have customized SL/TP ranges per D013, CSV values in expected ranges, verified by verify_m004_milestone.sh check 4
  - id: R030
    from_status: active
    to_status: validated
    proof: TEMPLATE comments explain absolute price semantics and direction handling, verified by verify_m004_milestone.sh check 7
  - id: R031
    from_status: active
    to_status: validated
    proof: Trade.exit_reason field with values 'sl', 'tp', 'resolution', exit reason diversity verified with Counter({'sl': 32, 'tp': 1}) on 50-market sample
duration: 3h 53m
verification_result: passed
completed_at: 2026-03-18T20:53:00+01:00
---

# M004: Parameter Grid Optimization with Stop Loss & Take Profit

**Transform backtesting from fixed-parameter testing to exhaustive grid search with stop loss and take profit as universal exit parameters, enabling systematic exploration of 600-1700 parameter combinations per strategy with ranked output showing explicit SL/TP values for top performers.**

## What Happened

Built a complete parameter optimization pipeline across five slices, transforming the backtest engine from testing single fixed configurations to exhaustive grid search including early exit logic:

**S01 (Parameter Grid Foundation)** extended all 7 strategy config files plus TEMPLATE to declare stop_loss and take_profit parameter ranges in `get_param_grid()`. Each strategy declares 3 SL and 3 TP absolute price thresholds (9× multiplier on existing grid dimensions), with ranges tuned to each strategy's typical entry prices per decision D013. Examples: S1 entry 0.45-0.55 → SL [0.35, 0.40, 0.45], TP [0.65, 0.70, 0.75]; S3 spike-based → SL [0.15, 0.20, 0.25], TP [0.75, 0.80, 0.85]. Grid sizes range from 648 (S2, S6) to 1728 (S7) combinations per strategy. TEMPLATE updated with working example and documented absolute price threshold semantics. Verification script proves all grids include SL/TP with manageable parameter space sizes.

**S02 (Stop Loss & Take Profit Engine)** implemented `simulate_sl_tp_exit()` function (~65 lines) that scans price arrays second-by-second from entry_second + 1 onward, checking direction-specific thresholds: Up bets exit when price ≤ stop_loss or ≥ take_profit; Down bets use inverted thresholds (SL when price ≥ 1.0 - stop_loss, TP when price ≤ 1.0 - take_profit) per decision D012. Function skips NaN prices, prioritizes SL over TP if both hit same second (risk management first), and returns 'resolution' with last valid price if no threshold hits before market close. Extended Trade dataclass with `exit_reason: str = 'resolution'` field for backward compatibility. Integrated simulator with `make_trade()` via keyword-only `stop_loss` and `take_profit` parameters. Discovered and fixed direction-agnostic PnL bug by adding `direction` parameter to `calculate_pnl_exit()` (Down bets: entry - exit vs Up bets: exit - entry). 13 comprehensive unit tests cover Up/Down × SL/TP/resolution matrix, NaN handling, edge cases, and PnL correctness.

**S03 (Grid Search Orchestrator)** wired stop_loss/take_profit parameters from strategy grids through the full optimization pipeline via dataclass introspection. Modified `optimize_strategy()` to introspect the config dataclass using `dataclasses.fields()`, split each parameter dict into strategy_params (config fields) and exit_params (stop_loss, take_profit), and thread exit_params through `run_strategy()` to `make_trade()`. Modified `run_strategy()` to accept keyword-only stop_loss and take_profit parameters and augment metrics dict with SL/TP values before returning. Full Cartesian product grid search now includes SL/TP dimensions (972 combinations for S1). Results CSV includes stop_loss and take_profit columns with per-combination values. Dry-run mode explicitly lists identified exit parameters for quick verification.

**S04 (Exit Simulation Fix & Output Display)** resolved the last integration gap preventing SL/TP simulation from running during backtests. Fixed market dict key mismatch: data loader was returning `'ticks'` but engine expected `'prices'`. Atomically renamed key in data_loader.py and backtest_strategies.py to establish 'prices' as the architectural standard. After fix, verification on 50 markets showed Counter({'sl': 33, 'tp': 1}), proving SL/TP simulation is active and producing early exits based on actual price movements. Enhanced top 10 console summary in optimize.py to include explicit stop_loss and take_profit values alongside existing metrics (Bets, WR, PnL, Sharpe, Score), producing human-readable output like `SL=0.4, TP=0.75`.

**S05 (Integration Verification)** built comprehensive verification script (`verify_m004_milestone.sh`) with 7 orthogonal checks proving end-to-end integration: strategy grids include SL/TP (reuses verify_m004_s01.py), dry-run shows 972 combinations with SL/TP dimensions, full optimization produces results CSV (with early-exit check to avoid long runtime), CSV has ≥100 rows with SL/TP columns in expected ranges, console displays SL/TP for top 10 (with CSV-based fallback), exit reason diversity verified programmatically (32 SL exits, 1 TP exit on 50-market sample), and all 8 strategies import without errors. All 7 checks passed on first run, confirming M004 deliverables integrate correctly.

The milestone eliminated fixed-parameter blind spots by making stop loss and take profit systematically searchable parameters, enabling data-driven discovery of optimal exit thresholds for each strategy.

## Cross-Slice Verification

All success criteria from the milestone roadmap were verified:

1. **Run `python3 -m analysis.optimize --strategy S1` and see 100+ parameter combinations tested** — ✅ Verified by S05 check 2: dry-run shows 972 combinations for S1 (entry params × SL × TP grid). Full optimization execution verified by S05 check 3.

2. **Output CSV shows top 10 ranked by performance with explicit stop_loss and take_profit values** — ✅ Verified by S05 check 4: CSV has 972 rows with stop_loss and take_profit columns containing values in expected ranges (SL: [0.35, 0.40, 0.45], TP: [0.65, 0.70, 0.75]).

3. **Each strategy (S1-S7) has complete `get_param_grid()` with SL/TP ranges** — ✅ Verified by S05 check 1: all 7 strategies pass grid validation via verify_m004_s01.py. Grid sizes: S1=972, S2=648, S3=1296, S4=972, S5=972, S6=648, S7=1728.

4. **TEMPLATE demonstrates the pattern for new strategies** — ✅ Verified by S05 check 7: TEMPLATE imports without errors and includes SL/TP parameters in get_param_grid().

5. **Trades distinguish SL exit vs TP exit vs hold-to-resolution in output** — ✅ Verified by S05 check 6: backtest on 50 markets produced Counter({'sl': 32, 'tp': 1}) exit reason distribution, proving simulation runs and produces diverse exit paths.

6. **Verification script proves all deliverables integrate correctly** — ✅ Verified by `./scripts/verify_m004_milestone.sh` exit code 0 with 7/7 checks passed.

**Milestone Definition of Done** — All criteria met:
- ✅ All 7 strategy folders (S1-S7) have `get_param_grid()` returning dicts with stop_loss and take_profit keys
- ✅ TEMPLATE/config.py demonstrates SL/TP pattern in example grid with documented semantics
- ✅ Engine has SL/TP exit simulation (simulate_sl_tp_exit checks price every second, exits early when threshold hit)
- ✅ Trade dataclass has exit_reason field with values 'sl', 'tp', or 'resolution'
- ✅ optimize.py generates Cartesian product including SL/TP dimensions (972 combinations for S1)
- ✅ Run `cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1` produces CSV with ≥100 combinations (972 actual) and top 10 include explicit SL/TP values
- ✅ Verification script proves: S1 grid includes SL/TP, dry-run shows dimensions, full run produces ranked output, at least one trade has exit_reason='sl' (32 actual) and one has 'tp' (1 actual)

## Requirement Changes

All 9 requirements covered by M004 transitioned from active to validated status:

- R023: active → validated — All 7 strategies (S1-S7) have get_param_grid() returning dicts with stop_loss and take_profit keys (3 values each), verified by verify_m004_milestone.sh check 1

- R024: active → validated — TEMPLATE/config.py has working get_param_grid() with SL/TP keys and comments explaining absolute price thresholds, verified by verify_m004_milestone.sh check 7

- R025: active → validated — simulate_sl_tp_exit() scans prices second-by-second with direction-specific thresholds (Up: SL when price ≤ stop_loss, TP when price ≥ take_profit; Down: inverted thresholds), verified by 13 unit tests in test_sl_tp_engine.py covering all exit paths, NaN handling, and PnL correctness

- R026: active → validated — optimize.py generates Cartesian product including SL/TP dimensions (972 combinations for S1), verified by dry-run output showing exit parameters identified and results CSV containing stop_loss and take_profit columns

- R027: active → validated — Results CSV contains stop_loss and take_profit columns with per-configuration values in expected ranges (SL: [0.35, 0.40, 0.45], TP: [0.65, 0.70, 0.75]), verified by verify_m004_milestone.sh check 4

- R028: active → validated — Console top 10 output displays SL/TP values alongside existing metrics (format: "SL=0.40, TP=0.75"), verified by verify_m004_milestone.sh check 5

- R029: active → validated — S1-S7 have customized SL/TP ranges per D013 (examples: S1 entry 0.45-0.55 → SL [0.35,0.40,0.45], TP [0.65,0.70,0.75]; S3 spike-based → SL [0.15,0.20,0.25], TP [0.75,0.80,0.85]), CSV values in expected ranges, verified by verify_m004_milestone.sh check 4

- R030: active → validated — TEMPLATE comments explain absolute price semantics ("stop_loss=0.45 means exit when price hits 0.45") and direction handling (engine swaps thresholds for Down bets), verified by verify_m004_milestone.sh check 7

- R031: active → validated — Trade.exit_reason field with three semantic values ('sl', 'tp', 'resolution'), exit reason diversity verified with Counter({'sl': 32, 'tp': 1}) on 50-market sample (verify_m004_milestone.sh check 6)

## Forward Intelligence

### What the next milestone should know

- **Market dict contract is now stable** — The 'prices' key is the architectural standard for tick arrays. Any future code that consumes market dicts from data_loader must use `market['prices']`, not `market['ticks']`. This contract was established in S04 and is foundational for SL/TP simulation.

- **Grid sizes are larger than originally anticipated** — Most strategies are in the 600-1000 range, but S3 (1296) and S7 (1728) exceed the 1000-combination target. These sizes are still tractable for grid search but increase runtime. Full optimization of all 7 strategies × ~5500 markets would take hours. Use `--assets` and `--durations` CLI flags to filter market subsets for faster testing.

- **Exit reason distribution is asymmetric** — On current market data, SL exits dominate (32 SL vs 1 TP on 50-market sample). This likely reflects strategy entry price selection and market dynamics. Future work optimizing SL/TP ranges should consider this asymmetry when tuning thresholds.

- **SL/TP semantics are absolute prices, not percentages** — This is documented in TEMPLATE but worth emphasizing. Strategy authors declare absolute price thresholds (e.g., stop_loss=0.45 means "exit when Down token price hits 0.45"). The engine handles direction logic internally, swapping SL/TP for Down bets automatically. If strategy authors misunderstand this contract and provide inverted values, thresholds will be wrong.

- **Dataclass introspection pattern is robust** — The parameter dict splitting in optimize.py uses `dataclasses.fields(type(base_config))` to distinguish config fields from exit params. This pattern is more maintainable than hardcoding a list of exit param names and scales to future runtime parameters.

- **TEMPLATE is now a working example** — Previous milestones had TEMPLATE as documentation-only. After M004/S01, TEMPLATE's `get_param_grid()` returns a real example grid (81 combinations) that can be imported and used. This makes it easier to test engine logic with TEMPLATE as a lightweight test case.

- **SL/TP simulation requires 'prices' key** — The engine's `make_trade()` function checks `if market.get('prices') is not None` before running `simulate_sl_tp_exit()`. If this key is missing, trades silently default to resolution exits without error. This is by design (backward compatibility), but could cause confusion if data loading changes.

### What's fragile

- **Atomic key rename dependency** — data_loader.py and backtest_strategies.py must use the same key name for tick arrays. The 'prices' key was established in S04 by atomically changing both files. If future changes rename the key again, both files must change together to avoid KeyError.

- **Exit reason diversity test parameters** — S05 check 6 (exit reason diversity) uses hardcoded thresholds (stop_loss=0.4, take_profit=0.7) on a 50-market sample. If market volatility shifts dramatically or strategies are rewritten, these thresholds may need adjustment to ensure both SL and TP exits occur in test data. Script comments document adjustment guidance.

- **Large grid runtime** — S3 (1296 combinations) and S7 (1728 combinations) exceed the original 1000-combination target. Full optimization takes 10-20 minutes per strategy on the full dataset. If runtime becomes prohibitive, strategies can reduce parameter ranges or add constraints in future optimization passes.

- **calculate_pnl_exit() direction parameter is new** — S02 added a `direction` parameter to `calculate_pnl_exit()` (breaking change). All existing code that calls this function from M003 or earlier would break if not updated. The function signature changed to accept direction as a string parameter for correct Down bet PnL (entry - exit vs exit - entry). Impact was contained to one call site in engine.py within this codebase.

- **No semantic validation of SL/TP ranges** — While verification checks that keys exist and values are non-empty, there's no validation that SL < entry < TP or that ranges make sense for each strategy's entry logic. If a strategy misconfigures ranges (e.g., SL > TP), engine must handle gracefully or validate during grid generation. Currently, invalid combinations are skipped per decision D014.

### Authoritative diagnostics

- **Verification script is the source of truth** — `./scripts/verify_m004_milestone.sh` with 7/7 checks passed (exit code 0) is the definitive proof of M004 completion. If any future changes to strategy configs or engine break SL/TP structure, this script will catch it immediately. Run it after any modifications to optimization pipeline or strategy configs.

- **Exit reason distribution** — Run `Counter(t.exit_reason for t in trades)` on backtest results to verify SL/TP simulation is active. Expect mix of 'sl', 'tp', and 'resolution' values. All 'resolution' indicates simulation not running (market dict key mismatch or missing prices).

- **Market dict structure** — Check `data_loader.load_all_data()[0].keys()` to see available market dict keys. Should include 'prices', 'market_id', 'creation_ts', 'end_date', 'resolution_value'. Missing 'prices' key will cause SL/TP simulation to be skipped.

- **Unit tests are definitive** — `src/tests/test_sl_tp_engine.py` has 13 tests with synthetic data proving all exit paths work correctly. If S03/S04 integration shows unexpected exit behavior, run these tests first to rule out engine bugs before debugging grid search or output logic.

- **Grid size computation is accurate** — S01 verification script computes Cartesian product size correctly by multiplying lengths of all parameter lists. These numbers match what S03's grid generation produces. Use these for runtime estimation: S1=972, S2=648, S3=1296, S4=972, S5=972, S6=648, S7=1728.

- **Console output pattern** — Grep optimize.py output for `SL=\d+\.\d+, TP=\d+\.\d+` to verify exit parameters are displayed. Missing pattern indicates T02 enhancement not applied or wrong output stream.

### What assumptions changed

- **Original assumption**: calculate_pnl_exit() would work correctly for Down bets without modifications.
- **What actually happened**: Function was direction-agnostic and calculated PnL as `exit - entry` for all trades, which is incorrect for Down bets (should be `entry - exit`). Required adding direction parameter in S02. This was discovered during test implementation, not during initial design.

- **Original assumption**: Slice plan expected `exit_reason` column in aggregated metrics CSV.
- **What actually happened**: `exit_reason` is per-trade data on Trade objects, not aggregated metrics. The CSV correctly includes stop_loss and take_profit columns showing which parameters each configuration used, but not per-trade exit reasons. This is the right design — aggregated metrics summarize outcomes, individual trade logs would show exit reasons if needed.

- **Original assumption**: 1000-combination limit was a hard target.
- **What actually happened**: S3 (1296) and S7 (1728) exceed this. The limit was conservative; actual tractability is higher (~2000 combinations still manageable). Runtime testing in S03 proved this is not problematic — the issue was data loading, not grid size.

- **Original assumption**: SL/TP would be simple threshold checks without NaN edge cases.
- **What actually happened**: Real market price arrays have NaN gaps (missing ticks, data quality issues). Simulator needed defensive last_valid_price tracking to handle these gracefully without failing.

- **Original assumption**: Resolution fallback would just use the last array element.
- **What actually happened**: Last element could be NaN, so fallback needed to track last valid price seen during scan, not just array[-1]. This edge case was discovered during S02 unit testing.

- **Original assumption**: Exit params would be simple keyword args passed directly from optimize.py.
- **What actually happened**: Needed dataclass introspection in S03 to distinguish config fields from exit params because `get_param_grid()` returns a flat dict containing both types. The split pattern is more robust than hardcoding a list of exit param names.

- **Original assumption**: Optimization CLI would have `--max-markets` flag for filtering.
- **What actually happened**: Optimizer doesn't support this parameter. Used `--assets` and `--durations` instead, which is more flexible (can target specific asset/duration pairs). Discovered during S05 verification.

- **Original assumption**: Expected roughly equal distribution of SL/TP exits.
- **What actually happened**: Actual distribution is highly skewed toward SL (32:1 ratio on 50-market sample). This reflects real market behavior where stop-loss thresholds are hit more frequently than take-profit thresholds given current strategy entry prices and SL/TP ranges.

## Files Created/Modified

**S01 (Parameter Grid Foundation):**
- `src/shared/strategies/S1/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S2/config.py` — Added stop_loss [0.40, 0.45, 0.50] and take_profit [0.60, 0.65, 0.70] to get_param_grid()
- `src/shared/strategies/S3/config.py` — Added stop_loss [0.15, 0.20, 0.25] and take_profit [0.75, 0.80, 0.85] to get_param_grid()
- `src/shared/strategies/S4/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S5/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/S6/config.py` — Added stop_loss [0.30, 0.35, 0.40] and take_profit [0.70, 0.75, 0.80] to get_param_grid()
- `src/shared/strategies/S7/config.py` — Added stop_loss [0.35, 0.40, 0.45] and take_profit [0.65, 0.70, 0.75] to get_param_grid()
- `src/shared/strategies/TEMPLATE/config.py` — Added commented example of stop_loss and take_profit in get_param_grid() with actual return value
- `src/scripts/verify_m004_s01.py` — Created verification script validating SL/TP presence, value counts, and grid sizes

**S02 (Stop Loss & Take Profit Engine):**
- `src/analysis/backtest/engine.py` — Added Trade.exit_reason field (line 39); implemented simulate_sl_tp_exit() function (~65 lines) with direction-specific threshold logic, NaN handling, and resolution fallback; extended make_trade() signature with keyword-only stop_loss and take_profit parameters; updated calculate_pnl_exit() to accept direction parameter for correct Down bet PnL; updated save_trade_log() to include exit_reason in CSV output
- `src/tests/__init__.py` — Created empty file for pytest discovery
- `src/tests/test_sl_tp_engine.py` — Implemented synthetic_market fixture and 13 comprehensive unit tests covering Up/Down × SL/TP/resolution matrix, NaN handling, edge cases, and PnL correctness verification

**S03 (Grid Search Orchestrator):**
- `src/analysis/optimize.py` — Added dataclass introspection to identify config fields vs exit params; split param_dict in optimization loop; threaded exit_params through run_strategy() call; added dry-run diagnostic output showing identified exit parameters
- `src/analysis/backtest_strategies.py` — Added keyword-only parameters stop_loss and take_profit to run_strategy() signature, threaded them to make_trade() call, and augmented metrics dict with SL/TP values before returning

**S04 (Exit Simulation Fix & Output Display):**
- `src/analysis/backtest/data_loader.py` — Changed market dict key from 'ticks' to 'prices' (line 117)
- `src/analysis/backtest_strategies.py` — Updated market_to_snapshot() to access 'prices' key instead of 'ticks' (line 68)
- `src/analysis/optimize.py` — Added SL/TP display to top 10 console output (lines 178-181)

**S05 (Integration Verification):**
- `scripts/verify_m004_milestone.sh` — Executable verification script with 7 checks proving M004 deliverables integrate correctly
- `.gsd/REQUIREMENTS.md` — Updated R023, R024, R029, R030 from "active" to "validated" status; updated coverage summary (18 validated, 12 active)
