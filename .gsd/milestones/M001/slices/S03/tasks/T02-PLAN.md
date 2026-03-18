---
estimated_steps: 5
estimated_files: 2
---

# T02: Rewire main.py import + build verification script

**Slice:** S03 — Trading adapter — live signals through shared strategies
**Milestone:** M001

## Description

Complete the integration by changing the one import in `trading/main.py` to use the new adapter, then build a comprehensive verification script that proves the entire chain works — from synthetic ticks through MarketSnapshot to executor-compatible Signal objects. The verification script follows the established pattern from `verify_s01.py` (18 checks) and `verify_s02.py` (18 checks).

This is the only task that modifies an existing file (`trading/main.py`), and it's a 1-line import change. R009 is enforced by a file hash integrity check in the verification script comparing executor.py, redeemer.py, and balance.py against the originals in the main repo.

**Important:** The verification script must run without any database or network access — it uses synthetic data, and it mocks `get_usdc_balance` and `already_traded_this_market` to avoid async/DB dependencies.

## Steps

1. **Rewire the import in `trading/main.py`:**
   Change line:
   ```python
   from trading.strategies import evaluate_strategies
   ```
   to:
   ```python
   from trading.strategy_adapter import evaluate_strategies
   ```
   This is the ONLY change to main.py. All other imports remain unchanged.

2. **Create `src/scripts/verify_s03.py`** with the standard header:
   ```python
   """S03 verification — trading adapter pipeline (no DB required).
   
   Run from src/ directory:
       cd src && PYTHONPATH=. python3 scripts/verify_s03.py
   """
   import sys
   passed = 0
   failed = 0
   def check(num, name, condition): ...  # same pattern as verify_s01.py
   ```

3. **Import checks (checks 1-3):**
   - Check 1: `from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot` succeeds
   - Check 2: `from shared.strategies import MarketSnapshot, Signal, get_strategy` succeeds
   - Check 3: `evaluate_strategies` is a coroutine function (`inspect.iscoroutinefunction`)

4. **Tick-to-snapshot conversion checks (checks 4-7):**
   Build synthetic data:
   - Create a mock MarketInfo with `started_at`, `ended_at` 300 seconds apart, `market_id`, `market_type`
   - Create synthetic Tick objects with known timestamps and up_prices
   - Include gaps (ticks missing for some seconds) to verify NaN handling
   
   Checks:
   - Check 4: `ticks_to_snapshot()` returns MarketSnapshot instance
   - Check 5: `snapshot.prices` shape is `(300,)` for 5-minute market
   - Check 6: NaN present for seconds with no ticks (`np.isnan(prices[gap_second])`)
   - Check 7: Known tick prices are at correct indices (`prices[known_second] == expected_price`)

5. **Strategy evaluation + signal field checks (checks 8-14):**
   Build spike-reversion synthetic data (calibrated per KNOWLEDGE.md — spike peak early at s=4-5, sharp reversion, entry_price ≤ 0.35):
   - Create MarketSnapshot with:
     - Prices ramp to 0.85 by s=4, hold, then revert sharply to 0.75 by s=14
     - `elapsed_seconds = 300` (full data for evaluation, as if post-market)
     - `total_seconds = 300`
   
   Checks:
   - Check 8: `get_strategy('S1').evaluate(snapshot)` returns Signal (not None)
   - Check 9: Signal direction is 'Down' (contrarian to up-spike)
   - Check 10: Signal has `signal_data` with `reversion_second` key
   
   Then test `_populate_execution_fields` or a simulated version:
   - Create a Signal as if returned by evaluate(), then verify field population
   - Check 11: `locked_shares > 0` after population
   - Check 12: `locked_cost > 0` after population
   - Check 13: `signal_data['price_min']` and `signal_data['price_max']` present
   - Check 14: `signal_data['profitability_thesis']` is a non-empty string

6. **Guard + edge case checks (check 15):**
   - Check 15: `ticks_to_snapshot()` with empty tick list produces all-NaN array without crashing

7. **Integrity + isolation checks (checks 16-18):**
   - Check 16: File hash of `trading/executor.py` matches the original in `/Users/igol/Documents/repo/polyedge/src/trading/executor.py` (proves R009 — no modifications)
   - Check 17: File hash of `trading/redeemer.py` and `trading/balance.py` match originals (proves R009)
   - Check 18: No `analysis.*` or `core.*` imports in `trading/strategy_adapter.py` (AST parse check, same pattern as verify_s02.py check 18)

8. **Run the verification script:**
   ```
   cd src && PYTHONPATH=. python3 scripts/verify_s03.py
   ```
   All checks must pass (exit code 0).

## Must-Haves

- [ ] `trading/main.py` import changed from `trading.strategies` to `trading.strategy_adapter` for `evaluate_strategies`
- [ ] `scripts/verify_s03.py` has 15+ checks covering imports, conversion, signal fields, guards, integrity, and isolation
- [ ] Verification script runs without DB or network access (uses synthetic data only)
- [ ] File hash integrity check proves executor.py, redeemer.py, balance.py are unmodified (R009)
- [ ] All verification checks pass (exit code 0)

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — all checks pass, exit code 0
- `grep "from trading.strategy_adapter import evaluate_strategies" src/trading/main.py` — returns 1 match
- `grep "from trading.strategies import evaluate_strategies" src/trading/main.py` — returns 0 matches

## Inputs

- `src/trading/strategy_adapter.py` — the adapter module built in T01 (must exist and import cleanly)
- `src/trading/main.py` — the bot's main loop that currently imports from `trading.strategies` (will be modified)
- `src/scripts/verify_s01.py` — pattern reference for verification script structure
- `src/scripts/verify_s02.py` — pattern reference for verification script structure
- `/Users/igol/Documents/repo/polyedge/src/trading/executor.py` — original file for hash comparison (R009 check)
- `/Users/igol/Documents/repo/polyedge/src/trading/redeemer.py` — original file for hash comparison
- `/Users/igol/Documents/repo/polyedge/src/trading/balance.py` — original file for hash comparison

### From KNOWLEDGE.md — S1 synthetic data calibration
When building synthetic data for S1 tests: place spike peak early (s=4-5), use sharp reversion (0.85→0.75 in 3-4 steps), ensure `entry_price ≤ 0.35`. Key thresholds: `spike_threshold_up=0.80`, `reversion_reversal_pct=0.10`, `min_reversion_ticks=10`, `entry_price_threshold=0.35`.

## Observability Impact

- **Import rewire:** `trading/main.py` now imports `evaluate_strategies` from `trading.strategy_adapter` instead of `trading.strategies`. Runtime behavior is identical in signature — the adapter's `evaluate_strategies` is an async function returning `list[Signal]`. The `[ADAPTER]` log prefix (from T01) now appears in the main bot loop's strategy evaluation cycle.
- **Verification script:** `scripts/verify_s03.py` provides a diagnostic surface — run `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` to verify the full pipeline (import chain, conversion, signal fields, integrity, isolation) with exit code 0/1.
- **Failure visibility:** If the import rewire is incorrect, the bot will crash on startup with `ImportError`. The verification script catches this in check 1 and exits immediately.
- **R009 enforcement:** File hash checks (16-17) will fail visibly if executor.py, redeemer.py, or balance.py are ever modified, providing continuous integrity verification.

## Expected Output

- `src/trading/main.py` — 1-line import change (from trading.strategy_adapter import evaluate_strategies)
- `src/scripts/verify_s03.py` — comprehensive verification script with 15+ checks, all passing
