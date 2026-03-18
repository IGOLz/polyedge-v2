---
id: M001
provides:
  - shared/strategies/ package with base types (StrategyConfig, MarketSnapshot, Signal, BaseStrategy), folder-based auto-discovery registry
  - S1 (spike reversion) and S2 (volatility) strategies ported as proof-of-concept tenants
  - TEMPLATE skeleton for creating new strategies by copy-and-customize
  - analysis/backtest_strategies.py — adapter bridging shared strategies into the existing backtest engine
  - trading/strategy_adapter.py — adapter bridging shared strategies into the live trading bot
  - scripts/parity_test.py — 24-assertion proof that identical data produces identical signals regardless of context
  - analysis/optimize.py — grid-search parameter optimizer with dry-run mode and ranking
  - get_param_grid() convention for strategy config modules enabling systematic parameter tuning
key_decisions:
  - D001: Strategy evaluate() is synchronous — works in both async trading and sync analysis contexts
  - D002: Elapsed seconds from market start as time axis — fixes tick-index-as-seconds bug
  - D004: MarketSnapshot uses numpy array indexed by elapsed second + metadata dict
  - D006: Shared Signal includes all fields trading executor expects — backward compatible
  - D008: Adapter composition pattern — new entry points compose shared.strategies + existing infrastructure, modifying neither
  - D009: Parity proven at pure strategy layer — strategies are pure functions on prices arrays
  - D010: Generic entry_second fallback chain (entry_second → reversion_second → 0) in Signal→Trade bridge
  - D011: TEMPLATE evaluate() returns None instead of NotImplementedError for parity_test safety
patterns_established:
  - Strategy folder convention — shared/strategies/{ID}/ with __init__.py, config.py (get_default_config), strategy.py (BaseStrategy subclass)
  - Adapter composition pattern — new module imports from both shared.strategies and existing infrastructure, composes them, modifies neither
  - Contract verification scripts — numbered check scripts (verify_s01.py, verify_s02.py, verify_s03.py, parity_test.py) as CI-ready health gates
  - NaN handling in strategies — ~np.isnan() mask → np.any(valid_mask) guard → valid_prices = window[valid_mask]
  - get_param_grid() convention on config modules — returns dict[str, list] for optimizer consumption
observability_surfaces:
  - "cd src && PYTHONPATH=. python3 scripts/verify_s01.py — 18-check S01 contract verification"
  - "cd src && PYTHONPATH=. python3 scripts/verify_s02.py — 18-check S02 adapter pipeline verification"
  - "cd src && PYTHONPATH=. python3 scripts/verify_s03.py — 18-check S03 trading adapter verification"
  - "cd src && PYTHONPATH=. python3 scripts/parity_test.py — 24-assertion parity proof"
  - "cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run — optimizer grid summary"
  - "discover_strategies() returns dict of all registered strategy IDs — inspectable for what loaded"
requirement_outcomes:
  - id: R001
    from_status: active
    to_status: validated
    proof: S1 and S2 each defined once in shared/strategies/ and consumed by both analysis (verify_s02.py 18/18) and trading (verify_s03.py 18/18) adapters. parity_test.py proves identical signals (24/24 checks).
  - id: R002
    from_status: active
    to_status: validated
    proof: shared/strategies/S1/ and S2/ exist with config.py + strategy.py; registry auto-discovers both; verify_s01.py confirms import isolation + discovery (18/18 checks).
  - id: R003
    from_status: active
    to_status: validated
    proof: parity_test.py check 8 proves strategies operate on array indices not elapsed_seconds — 60 prices with elapsed_seconds=45 produces identical signals to elapsed_seconds=60. Tick-count-as-time bug eliminated by construction.
  - id: R004
    from_status: active
    to_status: validated
    proof: Signal dataclass in shared/strategies/base.py used by both adapters. S1 and S2 produce Signal objects with all required fields. Parity test confirms identical Signal fields across contexts.
  - id: R005
    from_status: active
    to_status: validated
    proof: verify_s02.py proves full pipeline — market dict → MarketSnapshot → strategy.evaluate() → Signal → Trade → metrics (18/18 checks). CLI --help confirms module integrity.
  - id: R006
    from_status: active
    to_status: validated
    proof: verify_s03.py proves full pipeline — ticks → MarketSnapshot → strategy.evaluate() → Signal with all executor fields populated (18/18 checks).
  - id: R007
    from_status: active
    to_status: validated
    proof: parity_test.py 24/24 checks — S1 and S2 produce identical signals on identical prices regardless of elapsed_seconds. Covers signal parity, no-signal parity, multi-strategy consistency, array immutability, seconds-vs-ticks elimination.
  - id: R008
    from_status: active
    to_status: validated
    proof: discover_strategies() auto-discovers S1, S2, and TEMPLATE. Adding S2 required zero registry changes. parity_test.py check 6 auto-tests all discovered strategies.
  - id: R009
    from_status: active
    to_status: validated
    proof: verify_s03.py checks 16-17 — SHA-256 hashes of executor.py, redeemer.py, balance.py match originals. Only trading/main.py modified (1-line import change).
  - id: R010
    from_status: active
    to_status: validated
    proof: git diff --name-only HEAD -- src/core/ returns empty — zero files in src/core/ modified throughout the milestone.
  - id: R011
    from_status: active
    to_status: validated
    proof: TEMPLATE folder has 4 files, registry discovers it alongside S1/S2, evaluate() returns None (D011), parity_test.py check 6 auto-verifies it, README documents creation workflow. All 11 S05 checks pass.
  - id: R012
    from_status: active
    to_status: validated
    proof: python -m analysis.optimize --strategy S1 --dry-run prints grid (3×3×3=27 combos) and exits 0. get_param_grid() defined for S1 and S2. Optimizer skips TEMPLATE and strategies without param grids.
duration: 103m
verification_result: passed
completed_at: 2026-03-18
---

# M001: Unified Strategy Framework

**One strategy definition consumed identically by backtesting and live trading — shared/strategies/ package with base types, auto-discovery registry, two ported strategies, symmetric adapters for analysis and trading, parity proof, template skeleton, and parameter optimizer**

## What Happened

M001 delivered a complete unified strategy framework across 5 slices in ~103 minutes, eliminating the fundamental divergence between backtest and live trading strategy logic.

**S01 (22m)** established the foundation: `shared/strategies/` package with four core types — `StrategyConfig`, `MarketSnapshot` (numpy array indexed by elapsed second), `Signal` (all 10 executor-required fields with safe defaults), and `BaseStrategy` (ABC with `evaluate(snapshot) → Signal|None`). A folder-based registry (`discover_strategies()`, `get_strategy()`) auto-discovers strategies by scanning `shared/strategies/*/strategy.py`. S1 spike reversion was ported from `analysis/backtest/module_3_mean_reversion.py` with production M3_CONFIG parameters as the first concrete strategy. The package has zero imports from trading, analysis, or core — only stdlib and numpy.

**S02 (24m)** wired the analysis side: `analysis/backtest_strategies.py` (~160 lines) bridges shared strategies into the existing backtest engine via the adapter composition pattern (D008). `market_to_snapshot()` converts data_loader market dicts to MarketSnapshot, `run_strategy()` evaluates strategies and bridges Signal→Trade through the existing engine, and a CLI entry point supports `--strategy`, `--output-dir`, `--assets`, `--durations`. Zero modifications to any existing analysis file.

**S03 (23m)** wired the trading side symmetrically: `trading/strategy_adapter.py` converts live ticks to MarketSnapshot via `ticks_to_snapshot()` (NaN for missing seconds, last-write-wins for same-second ticks), evaluates all shared strategies via the registry, and populates all executor-required Signal fields. The single import in `trading/main.py` was rewired from `trading.strategies` to `trading.strategy_adapter`. Zero modifications to executor, redeemer, or balance.

**S04 (14m)** proved the framework works: S2 volatility strategy was ported from `trading/strategies.py::evaluate_m4_signal()`, and `scripts/parity_test.py` (24 assertions) demonstrated that identical price data produces identical signals regardless of adapter context. The key insight: strategies are pure functions on numpy arrays, so varying `elapsed_seconds` while keeping prices constant proves signals depend only on the data, not which adapter built the snapshot. The seconds-vs-ticks bug is eliminated by construction.

**S05 (20m)** completed the lifecycle: `shared/strategies/TEMPLATE/` provides a documented skeleton developers copy to create new strategies. `analysis/optimize.py` grid-searches a strategy's config space via `get_param_grid()` convention (3 params × 3 values = 27 combinations per strategy). Dry-run mode works without DB access.

The result is a full strategy lifecycle: create from TEMPLATE → implement evaluate() → backtest via `analysis.backtest_strategies` → optimize via `analysis.optimize` → deploy to live trading with identical behavior guaranteed.

## Cross-Slice Verification

Each success criterion from the roadmap was verified with concrete evidence:

**1. "A strategy defined in shared/strategies/S1/ produces identical signals when run through analysis and trading on the same price data"**
- ✅ VERIFIED: `scripts/parity_test.py` — 24/24 checks pass. S1 and S2 both produce identical signals with different `elapsed_seconds` values on identical price arrays. Checks 2-5 (S1 parity), checks 6-9 (S2 parity), check 8 (seconds-vs-ticks elimination) all pass.

**2. "New strategies can be created by copying shared/strategies/TEMPLATE/ and immediately work in both contexts"**
- ✅ VERIFIED: TEMPLATE folder contains 4 files (\_\_init\_\_.py, config.py, strategy.py, README.md). Registry discovers it alongside S1 and S2 (`discover_strategies()` returns `['S1', 'S2', 'TEMPLATE']`). `evaluate()` returns None safely. parity_test.py check 6 auto-verifies TEMPLATE without test changes.

**3. "The seconds-vs-ticks bug is eliminated — all strategies operate on elapsed-seconds-indexed data"**
- ✅ VERIFIED: parity_test.py check group 8 — 60 price points with `elapsed_seconds=45` fires identically to `elapsed_seconds=60` for both S1 and S2. Strategies index into `prices` array by integer position, not by elapsed time metadata. The bug is eliminated by construction (D002, D004).

**4. "Trading bot runs with shared strategies without regressions in executor/redeemer/balance"**
- ✅ VERIFIED: verify_s03.py checks 16-17 confirm SHA-256 hashes of executor.py, redeemer.py, and balance.py match originals. Only `trading/main.py` was modified (1-line import rewire). Check 18 confirms no analysis or core imports in the adapter.

**Definition of Done verification:**

| Criterion | Status | Evidence |
|-----------|--------|----------|
| shared/strategies/ contains base classes, registry, S1, S2, and TEMPLATE | ✅ | `find src/shared/strategies -type f` shows all expected files |
| Analysis adapter runs strategies via shared code and produces backtest results | ✅ | verify_s02.py 18/18 pass; CLI --help works |
| Trading adapter runs strategies via shared code and produces Signal objects the executor accepts | ✅ | verify_s03.py 18/18 pass; all executor fields populated |
| Parity test confirms identical signals on identical data | ✅ | parity_test.py 24/24 pass |
| Parameter optimization script can grid-search a strategy's config space | ✅ | `--dry-run` shows 27 combinations for S1 and S2 |
| src/core/ has zero modifications | ✅ | git diff shows no core changes |
| Trading executor, redeemer, balance, DB tables have zero modifications | ✅ | SHA-256 hash verification in verify_s03.py |

## Requirement Changes

- R001: active → validated — S1 and S2 each defined once, consumed by both adapters. parity_test.py 24/24 checks prove identical signals.
- R002: active → validated — S1/, S2/ folders with config + strategy modules; registry auto-discovers. verify_s01.py 18/18 checks.
- R003: active → validated — parity_test.py check 8: 60 prices with elapsed_seconds=45 fires identically to elapsed_seconds=60. Bug eliminated by construction.
- R004: active → validated — Single Signal dataclass used by both adapters with all executor fields. Parity test confirms identical fields.
- R005: active → validated — verify_s02.py 18/18: market dict → MarketSnapshot → evaluate → Signal → Trade → metrics pipeline proven.
- R006: active → validated — verify_s03.py 18/18: ticks → MarketSnapshot → evaluate → Signal with all executor fields populated.
- R007: active → validated — parity_test.py 24/24: identical signals regardless of context for both strategies.
- R008: active → validated — discover_strategies() auto-discovers S1, S2, TEMPLATE. Zero registry changes needed for S2.
- R009: active → validated — SHA-256 hashes of executor.py, redeemer.py, balance.py match originals. 1-line import change in main.py.
- R010: active → validated — git diff confirms zero src/core/ modifications.
- R011: active → validated — TEMPLATE folder with 4 files, auto-discovered, safe evaluate(), documented README.
- R012: active → validated — Optimizer CLI with dry-run mode, param grids for S1 and S2, 27 combinations each.
- R013: out-of-scope (unchanged) — Strategy logic ported as-is per D005; parameters are disposable.

## Forward Intelligence

### What the next milestone should know
- The full strategy lifecycle is operational: create from TEMPLATE → implement evaluate() → add get_param_grid() → backtest with `python -m analysis.backtest_strategies --strategy SN` → optimize with `python -m analysis.optimize --strategy SN` → deploy to live trading automatically via the shared registry.
- Import path for downstream work: `from shared.strategies import get_strategy, MarketSnapshot, Signal, discover_strategies`. PYTHONPATH must include `src/`.
- Both adapters are symmetric and follow the composition pattern (D008): `analysis/backtest_strategies.py` for historical data, `trading/strategy_adapter.py` for live ticks. Neither modifies its host infrastructure.
- All four verification scripts (`verify_s01.py`, `verify_s02.py`, `verify_s03.py`, `parity_test.py`) serve as regression gates — run all four to confirm framework health.

### What's fragile
- **Registry silent failure** — `discover_strategies()` silently skips broken strategy modules (no logging). A broken strategy folder disappears from the dict. Diagnosable by comparing `os.listdir('shared/strategies/')` vs `discover_strategies().keys()`, but a future logging integration would surface this automatically.
- **S1 synthetic data calibration** — verify_s01.py, verify_s02.py, and parity_test.py all use carefully calibrated price arrays tuned to S1's exact thresholds (spike_threshold_up=0.80, reversion_reversal_pct=0.10, entry_price_threshold=0.35). If S1 config changes, all test data needs recalibration.
- **py_clob_client mock requirement** — trading modules import `py_clob_client` which is not installed in the dev Python environment. All verification scripts mock it via `sys.modules`. New test tooling must follow the same pattern.
- **Worktree symlinks** — the development worktree relies on symlinks to main-repo trading modules. These are ephemeral and not git-tracked. The actual code changes are just the new files + 1-line main.py import change.

### Authoritative diagnostics
- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — definitive proof the framework delivers R007 (identical signals). If this breaks, the framework is wrong.
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py && python3 scripts/verify_s02.py && python3 scripts/verify_s03.py` — full contract verification across all three layers (shared, analysis adapter, trading adapter).
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.registry import discover_strategies; print(sorted(discover_strategies().keys()))"` — must show `['S1', 'S2', 'TEMPLATE']`.

### What assumptions changed
- **python3 not python** — system only has `python3` available. All commands and scripts use `python3`.
- **Worktree import resolution** — building in GSD worktrees requires symlinks for untracked main-repo modules. Documented in KNOWLEDGE.md as a reusable pattern.
- **No assumptions invalidated** — the milestone plan was accurate. Strategies are pure functions, parity was straightforward to prove, and the adapter composition pattern worked cleanly for both sides.

## Files Created/Modified

- `src/shared/__init__.py` — package init for shared module
- `src/shared/strategies/__init__.py` — re-exports 6 public names (BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy)
- `src/shared/strategies/base.py` — core types: StrategyConfig, MarketSnapshot (seconds-indexed numpy), Signal (10 executor fields), BaseStrategy ABC
- `src/shared/strategies/registry.py` — folder-based auto-discovery registry with diagnostic KeyError
- `src/shared/strategies/S1/__init__.py` — package init
- `src/shared/strategies/S1/config.py` — S1Config with M3 production parameters + get_default_config() + get_param_grid()
- `src/shared/strategies/S1/strategy.py` — S1Strategy: spike detection → reversion → contrarian signal on numpy arrays
- `src/shared/strategies/S2/__init__.py` — package init
- `src/shared/strategies/S2/config.py` — S2Config with M4 parameters + get_default_config() + get_param_grid()
- `src/shared/strategies/S2/strategy.py` — S2Strategy: volatility detection with spread/deviation guards
- `src/shared/strategies/TEMPLATE/__init__.py` — package init
- `src/shared/strategies/TEMPLATE/config.py` — TemplateConfig with example fields + get_default_config()
- `src/shared/strategies/TEMPLATE/strategy.py` — TemplateStrategy returning None + inline TODO guides
- `src/shared/strategies/TEMPLATE/README.md` — developer guide for creating new strategies
- `src/analysis/backtest_strategies.py` — adapter: market_to_snapshot(), run_strategy(), CLI entry point
- `src/analysis/optimize.py` — grid-search optimizer: param grid discovery, Cartesian product, backtest-and-rank, dry-run mode
- `src/trading/strategy_adapter.py` — adapter: ticks_to_snapshot(), _populate_execution_fields(), evaluate_strategies()
- `src/trading/main.py` — MODIFIED: 1-line import change (trading.strategies → trading.strategy_adapter)
- `src/scripts/verify_s01.py` — 18-check S01 contract verification
- `src/scripts/verify_s02.py` — 18-check S02 adapter pipeline verification
- `src/scripts/verify_s03.py` — 18-check S03 trading adapter verification
- `src/scripts/parity_test.py` — 24-assertion parity proof (R007)
