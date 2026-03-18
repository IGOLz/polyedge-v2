---
id: T02
parent: S01
milestone: M001
provides:
  - S1Strategy (spike reversion) as first concrete BaseStrategy implementation
  - S1Config with M3_CONFIG production parameter values
  - verify_s01.py verification script exercising full framework contract
key_files:
  - src/shared/strategies/S1/config.py
  - src/shared/strategies/S1/strategy.py
  - src/scripts/verify_s01.py
key_decisions:
  - Down-spike detection uses up_price ≤ spike_threshold_down (0.20) rather than the backtest's (1-min) >= spike_threshold pattern — equivalent but clearer
  - entry_price_threshold filter applied in evaluate() before returning Signal, matching production M3 behavior
patterns_established:
  - Strategy folder convention proven: S1/__init__.py + config.py + strategy.py auto-discovered by registry
  - NaN handling pattern: ~np.isnan() mask → np.any(valid_mask) guard → valid_prices = window[valid_mask]
  - signal_data carries detection metadata (spike_direction, peak price, reversion details); locked_* fields left at defaults for trading adapter
observability_surfaces:
  - evaluate() returns None for all no-signal conditions (no exception paths to catch)
  - signal_data keys (spike_direction, spike_max_price/spike_min_price, reversion_price, reversion_second) provide trade diagnostic context
  - verify_s01.py exit code 0/1 as automated contract check
duration: 12m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Port S1 spike reversion strategy and write verification script

**Ported spike reversion strategy (M3) as S1 in shared framework with 18-check verification script — all checks pass**

## What Happened

Read the three reference files from the main repo (`trading/constants.py` for M3_CONFIG values, `analysis/backtest/module_3_mean_reversion.py` for the algorithm, `trading/executor.py` for Signal field access patterns) and ported the spike reversion logic into the shared strategy framework.

Created `S1/config.py` with S1Config holding all M3_CONFIG parameters (spike_detection_window_seconds=15, spike_threshold_up=0.80, spike_threshold_down=0.20, reversion_reversal_pct=0.10, min_reversion_ticks=10, entry_price_threshold=0.35). Created `S1/strategy.py` with S1Strategy implementing `_find_spike()`, `_find_reversion()`, and `evaluate()` — all operating on numpy arrays with NaN masking. The strategy returns contrarian signals: up-spike → Down signal, down-spike → Up signal.

Key design choice during porting: the backtest's `_find_reversion` scans up to `min_reversion_seconds` which was configurable across a wide range (15-180). In M3_CONFIG the value is 10 (`min_reversion_ticks`), so I used that as the reversion window bound. The entry_price_threshold filter (≤ 0.35) was applied in `evaluate()` before Signal creation, matching what the production M3 strategy does.

The verification script test data required calibration: the plan's example had prices dropping to 0.50 after a 0.85 spike, giving entry_price = 1.0 - 0.50 = 0.50 which exceeds the 0.35 threshold. Adjusted reversion prices to 0.75 so entry_price = 0.25 ≤ 0.35.

## Verification

- `PYTHONPATH=. python3 scripts/verify_s01.py` — all 18 checks pass across 7 groups (imports, registry, spike detection, flat prices, NaN handling, Signal defaults, import isolation)
- `python3 -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"` → `S1_spike_reversion`
- All 4 slice-level verification commands pass (imports, registry, verify_s01.py, error_path)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` | 0 | ✅ pass | <1s |
| 2 | `cd src && PYTHONPATH=. python3 -c "from shared.strategies import get_strategy; s = get_strategy('S1'); print(s.config.strategy_name)"` | 0 | ✅ pass | <1s |
| 3 | `cd src && PYTHONPATH=. python3 -c "from shared.strategies import BaseStrategy, StrategyConfig, MarketSnapshot, Signal, discover_strategies, get_strategy"` | 0 | ✅ pass | <1s |
| 4 | `cd src && PYTHONPATH=. python3 -c "...assert s.config.strategy_id == 'S1'...print('registry: PASS')"` | 0 | ✅ pass | <1s |
| 5 | `cd src && PYTHONPATH=. python3 -c "...get_strategy('NONEXISTENT')...print('error_path: PASS')"` | 0 | ✅ pass | <1s |

## Diagnostics

- **Inspect S1 config:** `cd src && PYTHONPATH=. python3 -c "from shared.strategies import get_strategy; import dataclasses; s = get_strategy('S1'); print({f.name: getattr(s.config, f.name) for f in dataclasses.fields(s.config)})"`
- **Run full verification:** `cd src && PYTHONPATH=. python3 scripts/verify_s01.py`
- **Test specific signal:** Create a MarketSnapshot with custom prices array and call `s1.evaluate(snap)` — returns Signal or None

## Deviations

- Adjusted verification script test data: plan's reversion prices (0.72 at indices 20-30) were outside the min_reversion_ticks window (10) and would have produced entry_price 0.28 which works but at wrong indices. Changed to prices[8:15]=0.75 which is within the reversion window after the spike peak at index 3, giving entry_price=0.25.
- Down-spike detection simplified from `(1.0 - min_price) >= spike_threshold` to `min_price <= spike_threshold_down` using the pre-computed down threshold (0.20) rather than computing complement at runtime. Mathematically equivalent.

## Known Issues

None.

## Files Created/Modified

- `src/shared/strategies/S1/__init__.py` — empty package init
- `src/shared/strategies/S1/config.py` — S1Config dataclass with M3_CONFIG parameters + get_default_config()
- `src/shared/strategies/S1/strategy.py` — S1Strategy with evaluate(), _find_spike(), _find_reversion()
- `src/scripts/verify_s01.py` — 18-check verification script covering all contract requirements
- `.gsd/milestones/M001/slices/S01/tasks/T02-PLAN.md` — added Observability Impact section (pre-flight fix)
- `.gsd/milestones/M001/slices/S01/S01-PLAN.md` — marked T02 as [x]
