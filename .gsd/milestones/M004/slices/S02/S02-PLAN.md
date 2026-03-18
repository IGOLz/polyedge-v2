# S02: Stop Loss & Take Profit Engine

**Goal:** Engine simulates early exits when stop loss or take profit thresholds are hit, scanning price arrays second-by-second after entry and calculating correct PnL for all exit paths.

**Demo:** Call `make_trade()` with `stop_loss=0.45, take_profit=0.70` on synthetic market data where price drops below SL → Trade object has `exit_reason='sl'`, exit occurs at correct second with correct PnL. Run unit tests covering Up/Down × SL/TP × hit/miss → all pass.

## Must-Haves

- `Trade` dataclass has `exit_reason: str` field defaulting to 'resolution' for backward compatibility
- `simulate_sl_tp_exit(prices, entry_second, entry_price, direction, stop_loss, take_profit)` function scans price array and returns `(exit_second, exit_price, exit_reason)` tuple
- Up bet logic: SL hits when `price <= stop_loss`, TP hits when `price >= take_profit`
- Down bet logic: SL hits when `price >= 1.0 - stop_loss`, TP hits when `price <= 1.0 - take_profit` (engine swaps thresholds per D012)
- NaN price handling: skip invalid seconds, check next valid price
- `make_trade()` accepts optional `stop_loss=None, take_profit=None` parameters (keyword-only), calls simulator when both provided
- PnL calculation via existing `calculate_pnl_exit()` for early exits
- Unit tests in `src/tests/test_sl_tp_engine.py` prove correctness for all exit paths with synthetic numpy arrays

## Proof Level

- This slice proves: **contract verification** — unit tests with synthetic data prove SL/TP logic works correctly for all combinations
- Real runtime required: no (uses synthetic data; real market data integration happens in S03)
- Human/UAT required: no (deterministic logic with comprehensive test coverage)

## Verification

- `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v` → all tests pass
- Test coverage includes:
  - Up bet with SL hit (price drops below threshold) → exit_reason='sl', correct exit_second/price/PnL
  - Up bet with TP hit (price rises above threshold) → exit_reason='tp', correct exit_second/price/PnL
  - Down bet with SL hit (price rises above inverted threshold) → exit_reason='sl'
  - Down bet with TP hit (price drops below inverted threshold) → exit_reason='tp'
  - No threshold hit → hold to resolution, exit_reason='resolution'
  - NaN handling: skip invalid prices, exit when first valid threshold hit
  - Both SL and TP hit in same second → SL prioritized (risk management over profit taking)
  - PnL calculation matches expected for all exit paths (uses existing calculate_pnl_exit())
- Manual smoke test from research doc passes:
  ```python
  import numpy as np
  from analysis.backtest.engine import simulate_sl_tp_exit
  
  # Up bet, price drops to hit SL
  prices = np.array([0.55, 0.53, 0.48, 0.45, 0.40, 0.38])
  exit_sec, exit_price, reason = simulate_sl_tp_exit(
      prices, entry_second=0, entry_price=0.55, 
      direction='Up', stop_loss=0.45, take_profit=0.70
  )
  assert exit_sec == 3 and reason == 'sl'
  
  # Up bet, price rises to hit TP
  prices = np.array([0.55, 0.58, 0.62, 0.68, 0.72, 0.75])
  exit_sec, exit_price, reason = simulate_sl_tp_exit(
      prices, entry_second=0, entry_price=0.55,
      direction='Up', stop_loss=0.45, take_profit=0.70
  )
  assert exit_sec == 4 and reason == 'tp'
  ```
- Failure path diagnostic check:
  ```python
  # Verify simulator returns structured error state when no threshold hit
  cd src && python3 -c "
  import numpy as np
  from analysis.backtest.engine import simulate_sl_tp_exit
  prices = np.array([0.55, 0.56, 0.57, 0.58, 0.59, 0.60])
  exit_sec, exit_price, reason = simulate_sl_tp_exit(
      prices, entry_second=0, entry_price=0.55,
      direction='Up', stop_loss=0.45, take_profit=0.70
  )
  assert reason == 'resolution', f'Expected resolution, got {reason}'
  assert exit_sec == len(prices) - 1, f'Expected last second {len(prices)-1}, got {exit_sec}'
  print(f'✓ No-hit case returns: exit_sec={exit_sec}, exit_price={exit_price:.2f}, reason={reason}')
  "
  ```

## Observability / Diagnostics

- Runtime signals: Trade.exit_reason field distinguishes 'sl', 'tp', 'resolution' outcomes (visible in all Trade objects)
- Inspection surfaces: Unit tests print exit_reason for each test case; Trade objects directly inspectable in REPL
- Failure visibility: NaN handling logs skipped seconds (via test assertions); threshold detection failures surface immediately as assertion errors with price/threshold values
- Redaction constraints: none (backtest-only, no PII or secrets)

## Integration Closure

- Upstream surfaces consumed: S01 provides strategy grids with SL/TP parameter ranges (not directly consumed by engine, but defines the contract this slice implements)
- New wiring introduced in this slice: `make_trade()` calls `simulate_sl_tp_exit()` when SL/TP parameters provided; Trade.exit_reason field populated by simulator
- What remains before milestone is usable end-to-end: S03 must wire engine into optimize.py grid generation (extract SL/TP from strategy grids, pass to make_trade); S04 must add output formatting for exit_reason column

## Tasks

- [x] **T01: Trade dataclass extension and test infrastructure setup** `est:20m`
  - Why: Extend Trade with exit_reason field and create tests directory before implementing core logic
  - Files: `src/analysis/backtest/engine.py`, `src/tests/__init__.py`, `src/tests/test_sl_tp_engine.py`
  - Do: Add `exit_reason: str = 'resolution'` field to Trade dataclass; create `src/tests/` directory with empty `__init__.py`; create test file skeleton with pytest imports and fixture for synthetic market data; verify backward compatibility by importing Trade and checking default field value
  - Verify: `cd src && python3 -c "from analysis.backtest.engine import Trade; t = Trade(market_id='test', direction='Up', entry_price=0.50, exit_price=0.60, entered_at=0, exited_at=300, pnl=0.1, trade_amount=100.0); assert t.exit_reason == 'resolution'; print('✓ Trade.exit_reason defaults to resolution')"` succeeds
  - Done when: Trade dataclass has exit_reason field with 'resolution' default, tests directory exists with skeleton test file, backward compatibility verified

- [x] **T02: Implement simulate_sl_tp_exit() core function** `est:45m`
  - Why: Core engine logic for scanning prices and detecting SL/TP thresholds with direction handling
  - Files: `src/analysis/backtest/engine.py`
  - Do: Implement `simulate_sl_tp_exit(prices, entry_second, entry_price, direction, stop_loss, take_profit)` that: (1) scans prices from entry_second+1 to end; (2) for Up bets, checks if price <= stop_loss (SL) or price >= take_profit (TP); (3) for Down bets, inverts thresholds: SL when price >= 1.0 - stop_loss, TP when price <= 1.0 - take_profit; (4) skips NaN prices; (5) prioritizes SL over TP if both hit in same second; (6) returns (exit_second, exit_price, exit_reason) or (last_second, final_price, 'resolution') if no threshold hit
  - Verify: Manual smoke test from research doc (see slice verification section above) passes with both SL and TP scenarios
  - Done when: Function exists, handles Up/Down direction logic correctly, skips NaN prices, returns correct exit tuples

- [x] **T03: Integration with make_trade() and comprehensive unit tests** `est:1h`
  - Why: Wire simulator into trade creation flow and prove correctness with exhaustive test coverage
  - Files: `src/analysis/backtest/engine.py`, `src/tests/test_sl_tp_engine.py`
  - Do: Update `make_trade()` signature to accept `*, stop_loss=None, take_profit=None` (keyword-only after existing positional args); when both provided, call `simulate_sl_tp_exit()` and use returned values to populate Trade object; calculate PnL via existing `calculate_pnl_exit()`; write comprehensive unit tests covering: Up SL hit, Up TP hit, Down SL hit, Down TP hit, no hit (resolution), NaN handling, both hit same second (SL priority), PnL correctness for all paths
  - Verify: `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v` → all tests pass (minimum 8 test cases covering matrix of exit paths)
  - Done when: make_trade() accepts optional SL/TP parameters and calls simulator when provided, all unit tests pass proving R025 and R031 satisfied, PnL calculation reuses calculate_pnl_exit()

## Files Likely Touched

- `src/analysis/backtest/engine.py` — Trade dataclass extension, simulate_sl_tp_exit() implementation, make_trade() integration
- `src/tests/__init__.py` — Empty file for pytest discovery (new directory)
- `src/tests/test_sl_tp_engine.py` — Comprehensive unit tests with synthetic numpy arrays
