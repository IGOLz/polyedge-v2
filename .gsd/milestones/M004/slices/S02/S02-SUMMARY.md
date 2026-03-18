---
id: S02
parent: M004
milestone: M004
provides:
  - simulate_sl_tp_exit() function that scans prices second-by-second and detects SL/TP threshold hits
  - Trade.exit_reason field for distinguishing sl/tp/resolution exits in all Trade objects
  - make_trade() integration with optional stop_loss and take_profit parameters
  - Direction-aware PnL calculation for Down bets (entry - exit vs exit - entry)
  - Comprehensive unit test suite (13 tests) covering all exit paths, NaN handling, and PnL correctness
requires:
  - slice: S01
    provides: Strategy grids with stop_loss and take_profit keys (consumed by S03, not directly by engine)
affects:
  - S03 (consumes simulate_sl_tp_exit and Trade.exit_reason for grid search integration)
  - S04 (consumes exit_reason field for output formatting)
key_files:
  - src/analysis/backtest/engine.py
  - src/tests/test_sl_tp_engine.py
key_decisions:
  - none (followed D012 threshold logic from M004 research)
patterns_established:
  - Pure function pattern for simulation - no side effects, deterministic, testable in isolation
  - SL priority over TP when both hit same second (risk management first)
  - Keyword-only parameters for optional features (stop_loss=None, take_profit=None)
  - Direction parameter added to calculate_pnl_exit() for correct Down bet PnL
observability_surfaces:
  - Trade.exit_reason field (inspectable in REPL via print(trade) or vars(trade))
  - exit_reason included in CSV trade logs via save_trade_log()
  - Unit tests print descriptive assertion failures showing expected vs actual exit conditions
drill_down_paths:
  - .gsd/milestones/M004/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S02/tasks/T02-SUMMARY.md
  - .gsd/milestones/M004/slices/S02/tasks/T03-SUMMARY.md
duration: 1h 40m
verification_result: passed
completed_at: 2026-03-18T18:08:00+01:00
---

# S02: Stop Loss & Take Profit Engine

**Engine scans prices second-by-second for SL/TP threshold hits with direction-specific logic, extends Trade dataclass with exit_reason field, and integrates with make_trade() for early exit detection**

## What Happened

Built the core SL/TP simulation engine in three tasks:

**T01** extended Trade dataclass with `exit_reason: str = 'resolution'` field for backward compatibility and created test infrastructure (`src/tests/` directory with skeleton test file).

**T02** implemented `simulate_sl_tp_exit()` function (~65 lines) that scans price arrays from entry_second + 1 onward, checking direction-specific thresholds:
- **Up bets**: SL when price ≤ stop_loss, TP when price ≥ take_profit
- **Down bets**: Inverts thresholds (SL when price ≥ 1.0 - stop_loss, TP when price ≤ 1.0 - take_profit) per decision D012 because Down token price = 1.0 - up_price

Function skips NaN prices, prioritizes SL over TP if both hit same second (risk management first), and returns 'resolution' with last valid price if no threshold hits before market close.

**T03** integrated simulator with `make_trade()` by adding keyword-only `stop_loss` and `take_profit` parameters. When both provided, function calls `simulate_sl_tp_exit()` and uses returned exit_second, exit_price, and exit_reason to populate Trade object.

During test implementation, discovered that `calculate_pnl_exit()` was direction-agnostic and incorrectly calculated PnL for Down bets. Updated function to accept `direction` parameter and apply correct formula:
- **Up bets**: PnL = exit_price - entry_price (you bought Yes token)
- **Down bets**: PnL = entry_price - exit_price (you bought No token)

Wrote 13 comprehensive unit tests covering:
- Up/Down × SL/TP/resolution matrix (6 tests)
- Edge cases: NaN handling, both thresholds same second, boundary exits, all-NaN scenarios (4 tests)
- PnL correctness verification with hand-calculated expected values including direction-specific Down bet test (3 tests)

## Verification

All slice-level verification checks passed:

1. **Full test suite**: `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v` → 13 passed in 0.35s ✓
2. **Smoke tests from plan**:
   - Up bet SL hit: price drops to 0.45 → exits at second 3 with reason 'sl' ✓
   - Up bet TP hit: price rises to 0.72 → exits at second 4 with reason 'tp' ✓
   - No-hit case: no threshold → returns 'resolution' at last second with last valid price ✓
3. **Backward compatibility**: make_trade() without SL/TP parameters → exit_reason defaults to 'resolution' ✓

Test coverage verified all must-haves:
- Direction handling (Up vs Down threshold logic)
- NaN price handling (skips invalid seconds, tracks last valid price)
- Resolution fallback (no threshold hit → 'resolution' with last second)
- SL priority (both hit same second → SL wins)
- PnL calculation via calculate_pnl_exit() for all exit paths including Down bets

## Requirements Advanced

- R025 — validated (engine simulates SL/TP exits by tracking price every second)
- R031 — validated (trades distinguish SL/TP/resolution via exit_reason field)

## Requirements Validated

- **R025**: Engine simulates stop loss and take profit exits by tracking price every second
  - Proof: simulate_sl_tp_exit() scans prices array second-by-second, checks SL/TP thresholds with direction-specific logic, handles NaN prices, returns (exit_second, exit_price, exit_reason). Verified by 13 unit tests covering all exit paths.

- **R031**: Trades distinguish SL exit vs TP exit vs hold-to-resolution in output
  - Proof: Trade dataclass has exit_reason field with three semantic values ('sl', 'tp', 'resolution'). Field is populated by simulator and included in CSV output. Verified by unit tests showing correct exit_reason for all scenarios.

## New Requirements Surfaced

none

## Requirements Invalidated or Re-scoped

none

## Deviations

**Major deviation**: Added `direction` parameter to `calculate_pnl_exit()` function (breaking change).

**Reason**: Original implementation was direction-agnostic and incorrectly calculated PnL for Down bets as `exit - entry` for all trades. For Down bets, this is wrong because you're buying the No token (price = 1.0 - up_price), so PnL must be inverted to `entry - exit`.

**Impact**: All call sites of `calculate_pnl_exit()` now must pass `direction` parameter. Function was introduced in M003 and only used within `make_trade()` in this codebase, so impact is contained to one call site in engine.py.

**Test count**: Implemented 13 tests instead of plan's minimum 12 (added `test_pnl_down_bet_tp_exit` to verify Down bet PnL calculation).

## Known Limitations

- **No trailing stop loss**: Fixed SL/TP thresholds only. Trailing SL (R032) deferred to future milestone.
- **No live trading integration**: Backtest-only implementation. Live bot integration (R033) is out of scope for M004.
- **No partial exits**: All-or-nothing exit logic. No support for scaling out of positions.
- **No time-based exits**: Only price threshold and resolution. No "exit after N seconds" logic.

## Follow-ups

none

## Files Created/Modified

- `src/analysis/backtest/engine.py` — Added Trade.exit_reason field (line 39); implemented simulate_sl_tp_exit() function (~65 lines) with direction-specific threshold logic, NaN handling, and resolution fallback; extended make_trade() signature with keyword-only stop_loss and take_profit parameters; updated calculate_pnl_exit() to accept direction parameter for correct Down bet PnL; updated save_trade_log() to include exit_reason in CSV output
- `src/tests/__init__.py` — Created empty file for pytest discovery
- `src/tests/test_sl_tp_engine.py` — Implemented synthetic_market fixture and 13 comprehensive unit tests covering Up/Down × SL/TP/resolution matrix, NaN handling, edge cases, and PnL correctness verification

## Forward Intelligence

### What the next slice should know

- **simulate_sl_tp_exit() expects prices array indexed by elapsed seconds**: The function scans from `entry_second + 1` onward, so the prices array must be aligned with market seconds (not tick counts). This matches the MarketSnapshot contract established in M001.

- **Direction parameter is critical for PnL correctness**: All code that calls `calculate_pnl_exit()` or creates trades with SL/TP must pass the direction parameter. Down bets have inverted price semantics (Down token = 1.0 - up_price), so PnL formula is reversed.

- **exit_reason is now always present in Trade objects**: All downstream code (CSV writers, metric calculators, visualization) can rely on this field existing. Default is 'resolution' for backward compatibility.

- **SL/TP parameters are keyword-only in make_trade()**: When wiring grid search in S03, use `stop_loss=value, take_profit=value` syntax (not positional args). This prevents accidental parameter order bugs.

- **NaN handling is defensive**: If prices array has NaN gaps, simulator skips them and uses last valid price for threshold checks. No special handling needed in calling code.

### What's fragile

- **calculate_pnl_exit() direction parameter is new**: All existing code that calls this function from M003 or earlier will break if not updated. The function signature changed from `calculate_pnl_exit(entry_price, exit_price, direction_bool, fee)` to include direction as a string parameter. Any code outside `make_trade()` that calls this function will need updates.

- **Down bet threshold inversion relies on D012 contract**: The simulator assumes SL/TP values in strategy grids are expressed as Down token values (e.g., stop_loss=0.45 means "exit when Down price hits 0.45"). It inverts these to check against up_price array. If strategy authors misunderstand this contract and provide inverted values, thresholds will be wrong. TEMPLATE documentation is critical.

- **Last valid price fallback for all-NaN scenarios**: If all prices after entry are NaN, simulator uses entry_price as last_valid_price. This works for resolution fallback but could mask data quality issues. Consider adding a warning if too many NaN prices encountered.

### Authoritative diagnostics

- **Unit tests are the source of truth**: `src/tests/test_sl_tp_engine.py` has 13 tests with synthetic data proving all exit paths work correctly. If S03/S04 integration shows unexpected exit behavior, run these tests first to rule out engine bugs before debugging grid search or output logic.

- **Trade.exit_reason is always inspectable**: For any Trade object, `print(trade.exit_reason)` shows the exit path. In REPL or debugging, this is the fastest way to confirm SL/TP logic executed correctly.

- **Manual smoke test pattern**: For quick sanity checks, the pattern from slice verification works:
  ```python
  import numpy as np
  from analysis.backtest.engine import simulate_sl_tp_exit
  prices = np.array([...])
  exit_sec, exit_price, reason = simulate_sl_tp_exit(prices, 0, 0.55, 'Up', 0.45, 0.70)
  assert reason in ['sl', 'tp', 'resolution']
  ```

### What assumptions changed

- **Original assumption**: calculate_pnl_exit() would work correctly for Down bets without modifications.
- **What actually happened**: Function was direction-agnostic and calculated PnL as `exit - entry` for all trades, which is incorrect for Down bets (should be `entry - exit`). Required adding direction parameter.

- **Original assumption**: SL/TP would be simple threshold checks without NaN edge cases.
- **What actually happened**: Real market price arrays have NaN gaps (missing ticks, data quality issues). Simulator needed defensive last_valid_price tracking to handle these gracefully.

- **Original assumption**: Resolution fallback would just use the last array element.
- **What actually happened**: Last element could be NaN, so fallback needed to track last valid price seen during scan, not just array[-1].
