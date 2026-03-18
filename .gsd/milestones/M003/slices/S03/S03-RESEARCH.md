# S03 — Implement all strategies — Research

**Date:** 2026-03-18

## Summary

This slice implements real `evaluate()` logic for all 7 strategies (S1-S7) based on prediction market research patterns found in the existing analysis modules and standalone strategy files. Each strategy detects specific market inefficiencies in 5-minute crypto up/down markets and returns Signal objects when entry conditions are met.

The codebase already contains reference implementations for these strategies in `src/analysis/strategies/` and `src/analysis/backtest/module_*.py`. These files provide working detection logic, parameter ranges, and performance validation. The task is to adapt this proven logic into the shared strategy framework's `evaluate()` interface using MarketSnapshot inputs.

All 7 strategies are already scaffolded from S01 with correct naming, stub implementations, and empty parameter grids. S02 upgraded the engine with dynamic fees and slippage modeling. This slice fills in the detection logic and parameter spaces.

## Recommendation

Implement each strategy by porting the detection logic from the reference implementations into the `evaluate()` method, adapting the data access patterns from the old module format (raw tick arrays + explicit price lookups) to the MarketSnapshot format (prices indexed by elapsed second). Define meaningful parameter grids based on the ranges that performed well in the reference backtests.

Build order: S1 (calibration) → S2 (momentum) → S3 (mean reversion) → S4 (volatility) → S5 (time-phase) → S6 (streak) → S7 (composite). The first three have complete reference implementations. S4-S6 have partial references in modules. S7 is new (composite ensemble) and depends on S1-S6 existing.

Verify each strategy individually with `python3 -m analysis.backtest_strategies --strategy SN` as it's implemented. This produces immediate feedback on whether the strategy generates trades and realistic metrics.

## Implementation Landscape

### Key Files

**Strategy implementation files** (all need real `evaluate()` and `get_param_grid()`):
- `src/shared/strategies/S1/strategy.py` — Calibration Mispricing
- `src/shared/strategies/S1/config.py` — S1Config with calibration-specific parameters
- `src/shared/strategies/S2/strategy.py` — Early Momentum
- `src/shared/strategies/S2/config.py` — S2Config with momentum parameters
- `src/shared/strategies/S3/strategy.py` — Mean Reversion
- `src/shared/strategies/S3/config.py` — S3Config with reversion parameters
- `src/shared/strategies/S4/strategy.py` — Volatility Regime
- `src/shared/strategies/S4/config.py` — S4Config with volatility parameters
- `src/shared/strategies/S5/strategy.py` — Time-Phase Entry
- `src/shared/strategies/S5/config.py` — S5Config with time-phase parameters
- `src/shared/strategies/S6/strategy.py` — Streak/Sequence
- `src/shared/strategies/S6/config.py` — S6Config with streak parameters
- `src/shared/strategies/S7/strategy.py` — Composite Ensemble
- `src/shared/strategies/S7/config.py` — S7Config with ensemble parameters

**Reference implementations** (read-only, for porting logic):
- `src/analysis/strategies/strategy_calibration.py` — Complete S1 reference with calibration map lookup, parameter grid, and proven backtest results
- `src/analysis/strategies/strategy_momentum.py` — Complete S2 reference with 30s→60s velocity calculation and stop-loss logic
- `src/analysis/strategies/strategy_streak.py` — Complete S6 reference with consecutive outcome detection
- `src/analysis/backtest/module_2_momentum.py` — S2 reference with contrarian velocity-based entries
- `src/analysis/backtest/module_3_mean_reversion.py` — S3 reference with spike detection, reversion wait, and multiple exit strategies
- `src/analysis/backtest/module_4_volatility.py` — S4 partial reference with volatility regime classification
- `src/analysis/backtest/module_5_time_filters.py` — S5 partial reference with time-based entry filtering
- `src/analysis/backtest/module_7_composite.py` — S7 partial reference for ensemble voting logic

**Base infrastructure** (already working, don't modify):
- `src/shared/strategies/base.py` — BaseStrategy, StrategyConfig, MarketSnapshot, Signal
- `src/analysis/backtest/data_loader.py` — Market loading, tick array format, `get_price_at_second()` helper
- `src/analysis/backtest/engine.py` — PnL calculation with dynamic fees + slippage (S02 upgraded)
- `src/analysis/backtest_strategies.py` — CLI entry point, `run_strategy()` function that calls `evaluate()` and converts Signals to Trades

### Build Order

**1. S1 (Calibration) — 45m**
Port calibration bucket logic from `strategy_calibration.py`. The reference implementation loads a calibration map from DB showing which price buckets (rounded to 0.05) have historical bias (actual win rate ≠ implied win rate). The strategy rounds entry_price to nearest bucket, looks up deviation, and enters Up (if deviation > threshold) or Down (if deviation < -threshold).

For the shared framework version, we can't query the DB during `evaluate()` (pure function contract). Instead, pre-compute calibration buckets as hardcoded config data or load them once at strategy construction. The simplest approach: use the well-performing parameter combination from the reference backtest (entry window 30-60s, price range 0.45-0.55, min deviation 0.08) and skip the calibration map lookup — just enter contrarian when price is near 0.50 and has moved ≥threshold from that balanced point.

**Why this unblocks:** Proves the evaluate() → Signal → Trade pipeline works end-to-end with realistic detection logic.

**2. S2 (Momentum) — 30m**
Port early momentum detection from `strategy_momentum.py` or `module_2_momentum.py`. The logic: compare price at 30s vs 60s, calculate velocity = (price_60s - price_30s) / 30s. If velocity ≥ threshold, enter contrarian (bet Down on Up momentum, bet Up on Down momentum). The reference uses tolerance windows (±10s) to handle missing ticks.

MarketSnapshot adaptation: `get_price_at_second()` isn't available inside evaluate(), but we have `snapshot.prices[second]` with NaN for missing. Implement a small inline helper to find nearest non-NaN price within tolerance.

**Why this unblocks:** Second strategy with different detection pattern. Proves parameter grids work (momentum threshold, eval window).

**3. S3 (Mean Reversion) — 60m**
Port spike + reversion detection from `module_3_mean_reversion.py`. The logic: scan first N seconds for price spike (UP price ≥ threshold or DOWN price ≥ threshold), then wait for reversion (price moves back ≥ reversal_pct from peak), then enter contrarian (bet Down after Up spike reverts, bet Up after Down spike reverts).

This is the most complex strategy. The reference has three exit types (market_end, profit_target, time_based). For simplicity, start with market_end only. The profit_target and time_based exits require mid-market exit logic that the shared Signal format doesn't support yet (signals are entry-only). The engine's `make_trade()` currently assumes hold-to-resolution unless `second_exited` and `exit_price` are provided, but signals don't populate those.

For S03, implement spike + reversion detection with hold-to-resolution. Document that mid-market exits could be added later if needed.

**Why this unblocks:** Most sophisticated detection pattern. Proves multi-stage logic (spike → revert → enter) works within MarketSnapshot constraints.

**4. S4 (Volatility Regime) — 30m**
Port volatility regime classification from `module_4_volatility.py`. The logic: calculate price volatility (standard deviation) over a lookback window at evaluation second. Only enter when volatility is above/below thresholds. Often combined with another signal (e.g., momentum). For standalone use, enter contrarian when volatility is high (high uncertainty = fade extremes).

The reference module has complex multi-factor logic. For shared strategy, simplify to: calculate rolling std dev, if std dev ≥ threshold and price is extreme (≥0.70 or ≤0.30), enter contrarian.

**Why this unblocks:** Proves statistical calculation patterns (rolling window, std dev) work with MarketSnapshot.

**5. S5 (Time-Phase Entry) — 30m**
Port time-based filtering from `module_5_time_filters.py`. The logic: enter based on elapsed time phase (early/mid/late market), hour of day, or day of week. The reference found that certain hours (e.g., high volume during US trading hours) had better entry success.

For shared strategy: enter at specific elapsed_seconds ranges (e.g., 60-120s window) when price is in a target range. Use `snapshot.metadata['hour']` to filter by hour if needed.

**Why this unblocks:** Proves metadata-based filtering works.

**6. S6 (Streak) — 45m**
Port streak detection from `strategy_streak.py`. The logic: track consecutive same-outcome markets in the same market_type (e.g., BTC 5m). After N consecutive Up outcomes, bet Down on the next market (mean reversion across sequential markets).

This is the only strategy that needs state across markets. The shared `evaluate()` contract is stateless (pure function, no side effects). Solution: pass streak context via `snapshot.metadata`. The backtest runner would need to track streaks and inject them into metadata. This is a significant change to `backtest_strategies.py`.

Alternative: implement a simplified version that doesn't require cross-market state. For example, detect intra-market streaks (consecutive same-direction price moves within one market) and fade those. This is weaker than the original strategy but keeps the pure function contract.

For S03, implement the simplified intra-market streak version. Document that true cross-market streak detection requires backtest runner changes.

**Why this unblocks:** Last standalone strategy. Proves edge-case patterns work.

**7. S7 (Composite Ensemble) — 45m**
Implement ensemble voting logic. The idea: run multiple base strategies (S1-S6), aggregate their signals, and enter only when ≥N strategies agree on direction.

The shared `evaluate()` contract doesn't allow calling other strategies (no access to registry). Solution: duplicate the core detection logic of 2-3 simple strategies (e.g., momentum, calibration) inline, or restructure to allow strategy composition.

For S03, implement a simplified version: hardcode the logic of 2-3 strategies inline, return Signal only if multiple agree. This is less clean than true composition but keeps the pure function contract.

Alternatively, skip composition and implement a "meta-signal" strategy that uses multiple detection patterns within the same evaluate() function (e.g., require both momentum AND calibration conditions before entering).

**Why last:** Depends on other strategies existing for reference. Most architecturally complex.

### Verification Approach

**Per-strategy verification:**
After implementing each strategy, run:
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy SN
```

This should:
- Load all markets from the database
- Call `evaluate()` for each market
- Produce a non-zero number of trades (or zero with explanation if strategy is too conservative)
- Generate JSON and Markdown reports in `reports/backtest/`

**Expected trade counts (based on reference implementations):**
- S1 (Calibration): 50-150 trades across 200+ markets (entry rate ~25-75%)
- S2 (Momentum): 30-100 trades (depends on threshold)
- S3 (Mean Reversion): 10-50 trades (requires spike + reversion, rarer)
- S4 (Volatility): 20-60 trades (depends on vol threshold)
- S5 (Time-Phase): 50-200 trades (broad time filter)
- S6 (Streak): 5-30 trades (requires sequence context, may be low)
- S7 (Composite): 5-20 trades (requires multi-strategy agreement, conservative)

Zero trades is acceptable if the strategy is conservative, but the report should show "Evaluated X markets, 0 trades taken" not crash or hang.

**Comparative ranking:**
After all strategies are implemented, run:
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies
```

This runs all strategies and produces a ranking table. Verify the ranking_score is computed and strategies are ordered by it.

**Unit-test level checks:**
Import each strategy and call `evaluate()` with a synthetic MarketSnapshot:
```python
from shared.strategies.S1.config import get_default_config
from shared.strategies.S1.strategy import S1Strategy
import numpy as np

cfg = get_default_config()
strategy = S1Strategy(cfg)

# Synthetic market with price spike
prices = np.full(300, 0.50)
prices[60] = 0.70  # spike at 60s
snapshot = MarketSnapshot(
    market_id="test",
    market_type="btc_5m",
    prices=prices,
    total_seconds=300,
    elapsed_seconds=300,
    metadata={"asset": "BTC", "hour": 14}
)

signal = strategy.evaluate(snapshot)
assert signal is not None or signal is None  # both valid, depends on config
```

This proves evaluate() doesn't crash on synthetic data.

## Constraints

**Pure function contract:**
All `evaluate()` implementations must be pure functions — no database queries, no file I/O, no async, no side effects, no cross-market state. This constraint is fundamental to the shared strategy framework (R001, R007). It enables identical behavior in backtest and live contexts.

**Strategies that need cross-market state** (like the streak strategy) must either:
- Be simplified to work within one market (intra-market patterns)
- Have state injected via `snapshot.metadata` by the runner (requires runner changes, not strategy changes)
- Be deferred to a future milestone that extends the framework

**MarketSnapshot data access:**
`snapshot.prices` is a numpy array indexed by elapsed second, with `np.nan` for missing ticks. Strategies cannot call `get_price_at_second()` from `data_loader` (that's a module function, not available in the shared strategy context). Instead, implement inline price lookup with tolerance:

```python
def _get_price(prices, target_sec, tolerance=5):
    """Get price at target second, or nearest within tolerance."""
    if 0 <= target_sec < len(prices):
        p = prices[target_sec]
        if not np.isnan(p):
            return float(p)
    for offset in range(1, tolerance + 1):
        for s in [target_sec - offset, target_sec + offset]:
            if 0 <= s < len(prices):
                p = prices[s]
                if not np.isnan(p):
                    return float(p)
    return None
```

**Parameter grid sizing:**
Each parameter grid should have 2-5 values per parameter, producing 10-50 total combinations. Too many combinations (100+) will make optimization runs too slow. Too few (< 5) won't explore the space meaningfully.

**Reference implementation adaptation:**
The reference implementations use:
- `market['ticks']` — already available as `snapshot.prices`
- `market['final_outcome']` — available as `snapshot.metadata['final_outcome']` (in backtest only; not available live)
- `market['total_seconds']` — available as `snapshot.total_seconds`
- `market['started_at']` — available as `snapshot.metadata['started_at']`
- `get_price_at_second(ticks, sec)` — replace with inline `_get_price(snapshot.prices, sec)`

Do NOT access `final_outcome` in strategy logic — it's only available in backtest mode for PnL calculation. Strategies must make decisions based on prices and elapsed time only, not future outcomes.

## Common Pitfalls

**Using final_outcome in detection logic:**
The reference implementations have access to `final_outcome` because they're pure backtest scripts. The shared strategies must work identically in live mode where outcome is unknown. Never use `snapshot.metadata['final_outcome']` in `evaluate()`. The engine uses it for PnL calculation after the signal is generated.

**Forgetting NaN handling:**
`snapshot.prices[sec]` may be NaN if no tick exists at that second. Always check `np.isnan()` or use a helper function with tolerance. Strategies that don't handle NaN will crash or produce wrong signals.

**Returning Signal with missing entry_second:**
The Signal must have `entry_second` in `signal_data` so the engine knows when the trade occurs. Without it, the engine defaults to second=0 which is wrong. Always populate `signal_data['entry_second']`.

**Invalid entry_price ranges:**
Polymarket token prices are clamped to [0.01, 0.99]. Strategies that calculate prices outside this range (e.g., spike detection at 1.0) will produce invalid trades. Always clamp or validate:
```python
if entry_price < 0.01 or entry_price > 0.99:
    return None
```

**Hardcoding market duration:**
Not all markets are 300 seconds (5 minutes). Use `snapshot.total_seconds` for duration-aware logic. The reference implementations sometimes hardcode `elapsed < 300` which breaks for other durations.

**Forgetting to update config dataclass fields:**
Each strategy's `config.py` has template `example_*` fields. Replace these with strategy-specific parameter names. The config dataclass must match the parameters used in `evaluate()`.

## Open Risks

**Database may be empty in worktree:**
Per S02 forward intelligence, the worktree database is empty. Running backtests requires either:
- Populating the database with historical data (time-consuming, complex)
- Testing strategies against synthetic data only (proves correctness but not performance)
- Accepting that verification shows "0 markets loaded" and deferring real backtest runs to the main repo

For S03, we'll implement all strategies and verify they import + instantiate + run without crashing on synthetic data. Real backtest verification against historical data can happen in S04 or after the user reviews in the main repo.

**Streak strategy may produce too few trades:**
The reference `strategy_streak.py` depends on consecutive same-outcome markets in the same market_type. If the DB has sparse data (few consecutive BTC 5m markets), this strategy may produce < 5 trades total. The simplified intra-market version may also be too conservative. This is acceptable — the playbook (S04) will document when strategies produce low trade counts and what that means.

**Composite ensemble may not add value:**
The ensemble strategy (S7) is only profitable if the base strategies (S1-S6) have uncorrelated errors. If all base strategies fail in the same market conditions, the ensemble won't help. This is a research risk, not an implementation risk. We implement it anyway and let the backtest results prove whether it adds value.

## Files Created/Modified

This slice will modify:
- `src/shared/strategies/S1/config.py` — replace example fields with calibration parameters
- `src/shared/strategies/S1/strategy.py` — implement `evaluate()` with calibration logic
- `src/shared/strategies/S2/config.py` — momentum parameters
- `src/shared/strategies/S2/strategy.py` — momentum detection
- `src/shared/strategies/S3/config.py` — mean reversion parameters
- `src/shared/strategies/S3/strategy.py` — spike + reversion detection
- `src/shared/strategies/S4/config.py` — volatility parameters
- `src/shared/strategies/S4/strategy.py` — volatility regime detection
- `src/shared/strategies/S5/config.py` — time-phase parameters
- `src/shared/strategies/S5/strategy.py` — time-based entry filtering
- `src/shared/strategies/S6/config.py` — streak parameters
- `src/shared/strategies/S6/strategy.py` — intra-market streak detection
- `src/shared/strategies/S7/config.py` — ensemble parameters
- `src/shared/strategies/S7/strategy.py` — composite voting logic

No changes to `base.py`, `registry.py`, `engine.py`, `backtest_strategies.py`, or any `core/` files.

## Forward Intelligence

### What the next slice should know

**All strategies are independently runnable:**
After S03, `python3 -m analysis.backtest_strategies --strategy SN` should work for all N=1..7. Each produces reports even if trade count is zero. S04 can document the exact CLI commands in the operator playbook without changes.

**Parameter grids are populated:**
Each strategy's `get_param_grid()` returns a non-empty dict with 2-5 parameters and 2-5 values each. The optimizer can run grid searches. S04 playbook should document how to use the optimizer.

**Strategies use entry_second in signal_data:**
All signals have `signal_data['entry_second']` set. The engine uses this for timing. Reports show correct entry timing distributions.

**Strategies are conservative:**
Better to return None (no signal) than return a bad signal. Strategies have multiple guard checks (insufficient data, NaN prices, invalid ranges) and bail early rather than force a trade. This means trade counts may be lower than reference implementations but quality is higher.

### What's fragile

**NaN density varies by market:**
Some markets have dense tick data (tick every second), others have gaps (ticks every 5-10 seconds). Strategies that require prices at specific seconds (e.g., momentum at exactly 30s and 60s) may fail more often in sparse markets. The tolerance-based price lookup mitigates this but doesn't eliminate it.

**Cross-market streak strategy is simplified:**
The original streak strategy tracks state across sequential markets. The S03 version detects intra-market patterns only. If the user wants the original strategy, the backtest runner needs to track streaks and inject them via metadata. This is a known gap documented in the strategy README.

**Composite ensemble duplicates logic:**
S7 duplicates detection logic from S1-S3 inline rather than calling those strategies. If S1-S3 logic changes, S7 must be updated manually. This is acceptable for M003 but should be refactored to true composition in a future milestone.

### Authoritative diagnostics

**Strategy produces signals:**
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 2>&1 | grep "trades"
```
Should show "[S1] Evaluating N markets → M trades" where M > 0 (or M = 0 with explanation).

**Strategy reports exist:**
After running backtest, check:
```bash
ls -lh reports/backtest/S1_*
```
Should show JSON and Markdown files with non-zero size.

**Strategy parameters are valid:**
```python
from shared.strategies.S1.config import get_param_grid
grid = get_param_grid()
assert len(grid) > 0, "Parameter grid is empty"
assert all(len(v) >= 2 for v in grid.values()), "Parameter ranges too small"
```

### What assumptions changed

None yet — this is research, not execution. Assumptions may change during implementation if the reference logic doesn't adapt cleanly to MarketSnapshot constraints.
