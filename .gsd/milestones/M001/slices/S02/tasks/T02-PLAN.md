---
estimated_steps: 4
estimated_files: 1
---

# T02: Create contract verification script for S02

**Slice:** S02 — Analysis adapter — backtest through shared strategies
**Milestone:** M001

## Description

Create `src/scripts/verify_s02.py` — a self-contained contract verification script that proves the adapter pipeline works end-to-end on synthetic data, without requiring a database connection. Follows the pattern established by `scripts/verify_s01.py` (read that file first for the print/check pattern and exit code convention).

The script builds synthetic market dicts that mimic `data_loader.load_all_data()` output, runs them through the full adapter pipeline (market_to_snapshot → strategy.evaluate → make_trade → compute_metrics), and asserts correctness at each stage.

## Steps

1. **Read `src/scripts/verify_s01.py`** to understand the established verification pattern: numbered checks with `[PASS]`/`[FAIL]` output, summary at end, exit code 0 on all pass / 1 on any failure.

2. **Create `src/scripts/verify_s02.py`** with the following check groups:

   **Import checks (checks 1-3):**
   - Import `market_to_snapshot`, `run_strategy`, `main` from `analysis.backtest_strategies`
   - Import `MarketSnapshot`, `Signal`, `get_strategy` from `shared.strategies`
   - Import `make_trade`, `compute_metrics` from `analysis.backtest.engine`

   **Conversion checks (checks 4-7):**
   - Build a synthetic market dict matching data_loader format:
     ```python
     import numpy as np
     from datetime import datetime, timezone
     
     prices = np.full(300, np.nan)  # 5-minute market = 300 seconds
     # Create a spike+reversion pattern that S1 will detect:
     # Up-spike in first 15 seconds: price goes to 0.85 (>= 0.80 threshold)
     for s in range(15):
         prices[s] = 0.50 + (0.35 * s / 14)  # ramp to 0.85
     # Reversion after spike: price drops back
     # Need entry_price <= 0.35: if price drops to 0.75, entry_price = 1.0 - 0.75 = 0.25 ✓
     for s in range(15, 30):
         prices[s] = 0.85 - (0.10 * (s - 14) / 15)  # gradual drop to ~0.75
     # Fill rest with stable prices
     for s in range(30, 300):
         prices[s] = 0.70
     
     synthetic_market = {
         'market_id': 'test-market-001',
         'market_type': 'BTC_5m',
         'asset': 'BTC',
         'duration_minutes': 5,
         'total_seconds': 300,
         'started_at': datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
         'ended_at': datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
         'final_outcome': 'Down',
         'hour': 12,
         'ticks': prices,
     }
     ```
   - Call `market_to_snapshot(synthetic_market)` — assert returns MarketSnapshot
   - Assert `snapshot.prices` is the numpy array with shape `(300,)`
   - Assert `snapshot.elapsed_seconds == 300` (backtest convention: full market)
   - Assert `snapshot.metadata['asset'] == 'BTC'` and other metadata fields present

   **Strategy evaluation checks (checks 8-11):**
   - Get S1 strategy: `strategy = get_strategy('S1')`
   - Call `strategy.evaluate(snapshot)` — assert returns a Signal (not None)
   - Assert Signal direction is 'Down' (contrarian to up-spike)
   - Assert `signal.signal_data['reversion_second']` is an int > 0

   **Trade pipeline checks (checks 12-15):**
   - Extract `second_entered = signal.signal_data['reversion_second']`
   - Call `make_trade(synthetic_market, second_entered, signal.entry_price, signal.direction)` — assert returns Trade
   - Assert Trade has correct direction matching Signal
   - Call `compute_metrics([trade], config_id='S1')` — assert returns dict with keys including `total_bets`, `win_rate_pct`, `total_pnl`
   - Assert `metrics['total_bets'] == 1`

   **Integration checks (checks 16-18):**
   - Call `run_strategy('S1', strategy, [synthetic_market])` — assert returns (trades_list, metrics_dict)
   - Assert trades_list has length >= 1
   - Verify no imports from `trading.*` or `core.*` in `analysis.backtest_strategies` by inspecting module source with `inspect.getsource()` or reading the file

3. **Add summary output** — print total passed/failed, exit 0 or 1.

4. **Run the script** to verify all checks pass: `cd src && PYTHONPATH=. python3 scripts/verify_s02.py`

**Critical calibration note from S01:** S1's entry_price_threshold is 0.35. The synthetic spike+reversion data must produce an entry_price ≤ 0.35, or evaluate() returns None. For an up-spike, entry_price = 1.0 - reversion_price, so reversion_price must be ≥ 0.65. Design the price curve so the reversion point has price ~0.75 (entry_price = 0.25, well within threshold).

## Must-Haves

- [ ] All import checks pass (adapter, shared strategies, engine)
- [ ] Synthetic market dict matches data_loader output format exactly (all required keys present)
- [ ] market_to_snapshot conversion verified (correct shape, elapsed_seconds, metadata)
- [ ] Full pipeline verified: market → snapshot → evaluate → Signal → Trade → metrics
- [ ] run_strategy() integration check passes
- [ ] Module isolation check: no trading/core imports in the adapter
- [ ] Script follows verify_s01.py pattern (numbered checks, pass/fail, exit code)

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — all checks pass, exit code 0

## Inputs

- `src/scripts/verify_s01.py` — Pattern reference: read this first for the check/print/exit convention
- `src/analysis/backtest_strategies.py` — The adapter created in T01 (market_to_snapshot, run_strategy, main)
- `src/shared/strategies/S1/strategy.py` — S1 evaluate() behavior: detects up-spike >= 0.80 in first 15 seconds, reversion_reversal_pct >= 0.10, entry_price <= 0.35
- `src/analysis/backtest/engine.py` — make_trade() and compute_metrics() signatures

## Observability Impact

- **Verification script exit code:** `scripts/verify_s02.py` exits 0 on full pipeline health, 1 on any failure — usable as a CI gate or agent health check.
- **Numbered check output:** Each check prints `[PASS]` or `[FAIL]` with a label, enabling line-level triage of adapter regressions.
- **Failure surface:** When the adapter or shared strategy breaks, the first failing check identifies the exact pipeline stage (import / conversion / evaluation / trade / integration / isolation).
- **No new runtime signals:** This task adds a test artifact, not runtime code. No new logs, metrics, or endpoints are introduced.

## Expected Output

- `src/scripts/verify_s02.py` — New file (~120-150 lines) with 16-18 numbered checks covering the full adapter contract. Runnable without DB. Exit code 0 on success.
