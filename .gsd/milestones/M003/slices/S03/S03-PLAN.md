# S03: Implement all strategies

**Goal:** Replace stub implementations with real signal detection logic for all 7 strategies (S1-S7) grounded in prediction market research patterns. Each strategy detects specific market inefficiencies and returns Signal objects when entry conditions are met.

**Demo:** Run `python3 -m analysis.backtest_strategies --strategy S1` (through S7) and each produces a JSON+Markdown report with trade counts, PnL metrics, and win rates. Strategies generate meaningful signals (or zero signals with valid explanation) when evaluated against market data.

## Must-Haves

- S1 (Calibration): Detects systematic mispricing near 50/50 prices, enters contrarian when price deviates from balanced
- S2 (Momentum): Calculates 30s→60s velocity, enters contrarian on strong directional moves
- S3 (Mean Reversion): Detects spike, waits for reversion, enters contrarian (hold-to-resolution only, no mid-market exits)
- S4 (Volatility Regime): Calculates rolling volatility, enters contrarian when volatility is high and price is extreme
- S5 (Time-Phase): Filters entry by elapsed time phase and optional hour-of-day constraints
- S6 (Streak): Simplified intra-market streak detection (consecutive same-direction price moves)
- S7 (Composite): Ensemble voting across multiple detection patterns, requires agreement from 2+ signals
- All strategies have meaningful parameter grids with 2-5 values per parameter (10-50 total combinations)
- All strategies return None for insufficient data (no crashes on sparse/NaN-heavy markets)
- All signals populate `entry_second` in signal_data
- Helper function for tolerance-based price lookup (handles NaN gracefully)

## Proof Level

- This slice proves: **integration** — strategies produce valid signals when consumed by backtest runner
- Real runtime required: yes (Python imports, strategy instantiation, synthetic data evaluation)
- Human/UAT required: no (automated verification proves correctness; user evaluates profitability after milestone completes)

## Verification

Run verification script that proves all strategies:
1. Import without errors
2. Instantiate with correct config
3. Have non-empty parameter grids
4. Run evaluate() on synthetic market snapshots without crashing
5. Return None or valid Signal objects
6. Populate entry_second when returning signals

Script: `bash scripts/verify_s03_strategies.sh`

Expected outcome:
- All 7 strategies pass import/instantiation checks
- All 7 parameter grids return dicts with 2+ parameters
- All 7 strategies handle synthetic data (spike pattern, flat prices, NaN-heavy data) without crashes
- Signals have required fields (direction, entry_price, entry_second in signal_data)

Database-dependent full backtests deferred to S04 or user verification (worktree DB is empty per S02 forward intelligence).

## Observability / Diagnostics

- **Runtime signals:** Strategy returns Signal or None; backtest runner reports trade count per strategy
- **Inspection surfaces:** 
  - `python3 -m analysis.backtest_strategies --strategy SN` produces reports/backtest/SN_*.json with metrics
  - Verification script tests strategies on synthetic MarketSnapshot objects and reports pass/fail
- **Failure visibility:** 
  - Import errors surface immediately in verification script
  - evaluate() crashes surface as Python exceptions with full traceback
  - NaN handling issues surface as unexpected None returns or wrong signals on synthetic data
- **Redaction constraints:** None (no secrets/PII in strategy logic)

## Integration Closure

- **Upstream surfaces consumed:**
  - `base.py`: BaseStrategy, StrategyConfig, MarketSnapshot, Signal
  - `registry.py`: discover_strategies(), get_strategy()
  - `backtest_strategies.py`: run_strategy(), market_to_snapshot()
  - `engine.py`: make_trade() with dynamic fees + slippage (from S02)
  
- **New wiring introduced in this slice:**
  - None — strategies plug into existing framework via evaluate() contract
  
- **What remains before milestone is truly usable end-to-end:**
  - S04: Operator playbook with CLI commands, metric interpretation, profitability thresholds
  - S04: Final verification script covering all M003 deliverables
  - User populates DB with historical data (or accepts synthetic-only verification)

## Tasks

- [x] **T01: Implement S1 (Calibration), S2 (Momentum), S3 (Mean Reversion)** `est:2h`
  - Why: These three have complete reference implementations and are foundational patterns; proves the evaluate() → Signal → Trade pipeline works with real detection logic
  - Files: `src/shared/strategies/S1/config.py`, `src/shared/strategies/S1/strategy.py`, `src/shared/strategies/S2/config.py`, `src/shared/strategies/S2/strategy.py`, `src/shared/strategies/S3/config.py`, `src/shared/strategies/S3/strategy.py`
  - Do:
    - Add `_get_price(prices, target_sec, tolerance=5)` helper to each strategy.py for NaN-aware price lookup
    - **S1 Calibration:** Port calibration logic from `strategy_calibration.py` — detect when entry_price is near 0.50 and has moved ≥threshold from balanced; enter contrarian (Up if price dropped below 0.45, Down if price rose above 0.55); eval window 30-60s; param grid: entry_window (30, 60, 90), price_threshold (0.45, 0.47, 0.50), min_deviation (0.05, 0.08, 0.10)
    - **S2 Momentum:** Port momentum detection from `strategy_momentum.py` — calculate velocity = (price_60s - price_30s) / 30s; if |velocity| ≥ threshold, enter contrarian; param grid: momentum_threshold (0.02, 0.03, 0.05, 0.08), eval_window_start (25, 30), eval_window_end (55, 60)
    - **S3 Mean Reversion:** Port spike+reversion logic from `module_3_mean_reversion.py` — scan first N seconds for spike (price ≥ spike_threshold), wait for reversion (price moves back ≥ reversal_pct from peak), enter contrarian; hold-to-resolution only (no mid-market exits); param grid: spike_threshold (0.70, 0.75, 0.80, 0.85), spike_lookback (15, 30, 60), reversion_pct (0.05, 0.08, 0.10, 0.15), min_reversion_sec (30, 60, 120)
    - All strategies must clamp entry_price to [0.01, 0.99] before returning Signal
    - All strategies must populate signal_data['entry_second']
    - Replace example_* config fields with strategy-specific parameters
  - Verify: 
    ```python
    from shared.strategies.S1.config import get_default_config, get_param_grid
    from shared.strategies.S1.strategy import S1Strategy
    import numpy as np
    cfg = get_default_config()
    s = S1Strategy(cfg)
    prices = np.full(300, 0.50); prices[60] = 0.70
    snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
    sig = s.evaluate(snap)
    assert sig is None or (sig.direction in ['Up','Down'] and 'entry_second' in sig.signal_data)
    grid = get_param_grid()
    assert len(grid) >= 2 and all(len(v) >= 2 for v in grid.values())
    ```
    Repeat for S2, S3.
  - Done when: All three strategies have real evaluate() implementations that handle synthetic price patterns without crashing; parameter grids return 10-50 combinations; imports work; spot-check evaluation returns None or valid Signal

- [x] **T02: Implement S4 (Volatility Regime), S5 (Time-Phase Entry)** `est:1h`
  - Why: These have partial references in modules; simplified standalone versions prove statistical calculation patterns work with MarketSnapshot
  - Files: `src/shared/strategies/S4/config.py`, `src/shared/strategies/S4/strategy.py`, `src/shared/strategies/S5/config.py`, `src/shared/strategies/S5/strategy.py`
  - Do:
    - Add `_get_price()` helper to both strategy.py files
    - **S4 Volatility:** Calculate rolling std dev over lookback window at eval_second; if std_dev ≥ threshold AND price is extreme (≥0.70 or ≤0.30), enter contrarian (Down if price high, Up if price low); param grid: lookback_window (30, 60, 90), vol_threshold (0.05, 0.08, 0.10), eval_second (60, 120, 180), extreme_price_threshold (0.70, 0.75, 0.80)
    - **S5 Time-Phase:** Enter based on elapsed_seconds range (early/mid/late) and optional hour filter; param grid: entry_window_start (30, 60, 90), entry_window_end (120, 180, 240), allowed_hours (list options: [10,11,12,13,14,15], [14,15,16,17,18], None for all hours), price_range_low (0.40, 0.45), price_range_high (0.55, 0.60)
    - Both strategies must handle insufficient data gracefully (return None if not enough ticks for calculation)
    - Replace example_* config fields with strategy-specific parameters
  - Verify: Same pattern as T01 — spot-check with synthetic data, verify parameter grids, confirm imports work
  - Done when: S4 and S5 have real evaluate() implementations; parameter grids return meaningful combinations; strategies handle edge cases (flat prices, NaN-heavy data, out-of-window eval_second)

- [x] **T03: Implement S6 (Streak/Sequence) simplified intra-market version** `est:45m`
  - Why: Original streak strategy requires cross-market state; this proves edge-case detection patterns work within pure function constraints
  - Files: `src/shared/strategies/S6/config.py`, `src/shared/strategies/S6/strategy.py`
  - Do:
    - Add `_get_price()` helper
    - Detect intra-market streaks: scan price movements in N-second windows; if K consecutive windows all move in same direction (all rising or all falling), enter contrarian on next window
    - Algorithm: divide elapsed time into window_size chunks, calculate direction (up/down/flat) for each chunk, count consecutive same-direction chunks, enter when streak_length ≥ threshold
    - Param grid: window_size (10, 15, 20, 30), streak_length (3, 4, 5), min_move_threshold (0.02, 0.03, 0.05) — min price change to count as directional move
    - Document in strategy docstring that this is simplified version; true cross-market streak detection requires backtest runner changes
    - Replace example_* config fields
  - Verify: Test on synthetic data with manufactured streaks (price rising for 4 consecutive windows); verify signal generated on 5th window
  - Done when: S6 detects intra-market streaks correctly; returns None when insufficient data or no streak detected; parameter grid returns 20-40 combinations

- [x] **T04: Implement S7 (Composite Ensemble) with inline multi-pattern detection** `est:1h`
  - Why: Last strategy, most architecturally complex; depends on understanding patterns from S1-S6
  - Files: `src/shared/strategies/S7/config.py`, `src/shared/strategies/S7/strategy.py`
  - Do:
    - Add `_get_price()` helper
    - Duplicate core detection logic from 2-3 simple strategies inline (calibration, momentum, volatility)
    - Run all detection patterns, collect signals (direction + confidence for each)
    - Return Signal only if ≥ min_agreement strategies agree on direction (e.g., 2 out of 3 say "Down")
    - Use median or max entry_price from agreeing signals
    - Param grid: min_agreement (2, 3), calibration_enabled (True, False), momentum_enabled (True, False), volatility_enabled (True, False), thresholds for each sub-pattern
    - Document in docstring that this duplicates logic from S1/S2/S4 inline rather than calling those strategies (pure function contract limitation)
    - Replace example_* config fields
  - Verify: Test on synthetic data where 2+ patterns trigger; verify composite signal generated; test cases where only 1 pattern triggers (should return None)
  - Done when: S7 generates signals only when min_agreement is met; returns None otherwise; parameter grid explores ensemble configuration space (10-30 combinations)

- [x] **T05: Write comprehensive verification script covering all strategies** `est:30m`
  - Why: Slice-level verification must prove all 7 strategies work correctly with automated checks before moving to S04
  - Files: `scripts/verify_s03_strategies.sh`
  - Do:
    - Check 1: Import all 7 strategies without errors
    - Check 2: Instantiate all 7 with default configs; verify strategy_id and strategy_name correct
    - Check 3: Call get_param_grid() for all 7; verify non-empty dicts with 2+ parameters each
    - Check 4: Evaluate all 7 on synthetic market snapshots:
      - Spike pattern (sudden price jump at 60s)
      - Flat prices (all 0.50)
      - NaN-heavy data (50% missing ticks)
      - Extreme prices (0.10, 0.90)
    - Check 5: Verify signals have required fields when returned (direction, entry_price, entry_second in signal_data, strategy_name)
    - Check 6: Verify strategies return None for insufficient data (< 10 valid ticks)
    - Use embedded Python for complex checks (same pattern as S01 verification script)
    - Print structured output: "✓ Strategy SN: passed M checks" or "✗ Strategy SN: failed at check K"
  - Verify: Run `bash scripts/verify_s03_strategies.sh`; expect exit code 0 with all checks passed
  - Done when: Verification script runs without errors; all 7 strategies pass all check groups; script exit code is 0

## Files Likely Touched

- `src/shared/strategies/S1/config.py` — S1Config with calibration parameters
- `src/shared/strategies/S1/strategy.py` — S1Strategy.evaluate() implementation
- `src/shared/strategies/S2/config.py` — S2Config with momentum parameters
- `src/shared/strategies/S2/strategy.py` — S2Strategy.evaluate() implementation
- `src/shared/strategies/S3/config.py` — S3Config with mean reversion parameters
- `src/shared/strategies/S3/strategy.py` — S3Strategy.evaluate() implementation
- `src/shared/strategies/S4/config.py` — S4Config with volatility parameters
- `src/shared/strategies/S4/strategy.py` — S4Strategy.evaluate() implementation
- `src/shared/strategies/S5/config.py` — S5Config with time-phase parameters
- `src/shared/strategies/S5/strategy.py` — S5Strategy.evaluate() implementation
- `src/shared/strategies/S6/config.py` — S6Config with streak parameters
- `src/shared/strategies/S6/strategy.py` — S6Strategy.evaluate() implementation
- `src/shared/strategies/S7/config.py` — S7Config with ensemble parameters
- `src/shared/strategies/S7/strategy.py` — S7Strategy.evaluate() implementation
- `scripts/verify_s03_strategies.sh` — comprehensive verification script
