---
estimated_steps: 6
estimated_files: 5
---

# T01: Port S2 volatility strategy and fix backtest adapter entry_second

**Slice:** S04 — Port S2 + parity verification
**Milestone:** M001

## Description

Create the S2 volatility strategy in `shared/strategies/S2/` by porting the M4 volatility detection logic from `trading/strategies.py::evaluate_m4_signal()`. S2 follows the exact same structure as S1 — `config.py` with dataclass config, `strategy.py` with `BaseStrategy` subclass, `__init__.py` empty. Also fix the backtest adapter's Signal→Trade bridge to handle S2's `entry_second` key generically.

The S2 strategy logic:
1. Guard: `len(prices) > eval_second` (need enough data)
2. Get `price = prices[eval_second]` — must not be NaN
3. Check base deviation: `abs(price - 0.50) >= base_deviation` (0.08)
4. Check spread: `min_spread (0.05) <= abs(2*price - 1) <= max_spread (0.50)`
5. Compute volatility: `np.nanstd(prices[eval_second - vol_window : eval_second + 1])` over valid (non-NaN) values, require >= 2 valid values
6. Check `volatility >= volatility_threshold` (0.05)
7. Contrarian direction: `price > 0.50` → Down (entry = 1-price), else Up (entry = price)
8. Return Signal with `signal_data` including `eval_second`, `spread`, `volatility`, `entry_second` (= eval_second)

Config parameters from `M4_CONFIG` in `trading/constants.py`: `eval_second=30`, `eval_window=2`, `volatility_window_seconds=10`, `volatility_threshold=0.05`, `min_spread=0.05`, `max_spread=0.50`, `base_deviation=0.08`.

## Steps

1. **Read S1 strategy files** to confirm the exact pattern: `src/shared/strategies/S1/config.py`, `src/shared/strategies/S1/strategy.py`, and `src/shared/strategies/base.py` for the base classes (StrategyConfig, BaseStrategy, MarketSnapshot, Signal).

2. **Read source M4 logic** from `src/trading/strategies.py` (the `evaluate_m4_signal()` function around lines 260-400) and `src/trading/constants.py` (the `M4_CONFIG` dict) to confirm parameter values and detection logic. Cross-reference with `src/analysis/backtest/module_4_volatility.py` for the volatility calculation.

3. **Create `src/shared/strategies/S2/__init__.py`** — empty file (matches S1 pattern).

4. **Create `src/shared/strategies/S2/config.py`** — Define `S2Config(StrategyConfig)` dataclass with all M4 parameters. Include `get_default_config()` function returning the default instance. Parameters: `eval_second=30`, `eval_window=2`, `volatility_window_seconds=10`, `volatility_threshold=0.05`, `min_spread=0.05`, `max_spread=0.50`, `base_deviation=0.08`. Set `strategy_id="S2"`, `strategy_name="Volatility"`.

5. **Create `src/shared/strategies/S2/strategy.py`** — Define `S2Strategy(BaseStrategy)` with `evaluate(snapshot: MarketSnapshot) -> Signal | None`. Implementation:
   - Import numpy, base classes, S2Config
   - Load config from `get_default_config()` in `__init__`
   - Guard: `len(snapshot.prices) > config.eval_second`
   - Get price at eval_second, check not NaN
   - Check `abs(price - 0.50) >= config.base_deviation`
   - Compute spread: `abs(2 * price - 1.0)`, check within `[min_spread, max_spread]`
   - Compute volatility: slice `prices[eval_second - volatility_window_seconds : eval_second + 1]`, filter NaN, require >= 2 valid, use `np.nanstd()` (population std dev, which is numpy default for nanstd)
   - Check `volatility >= config.volatility_threshold`
   - Determine direction: `price > 0.50` → "Down" (entry = 1-price), else "Up" (entry = price)
   - Return `Signal(strategy_id="S2", direction=direction, entry_price=entry_price, signal_data={"eval_second": config.eval_second, "spread": spread, "volatility": volatility, "entry_second": config.eval_second, "price_at_eval": price})`
   - Note: `np.nanstd()` uses ddof=0 by default (population std dev), matching both the trading manual calculation and analysis `np.std()`.

6. **Fix backtest adapter entry_second** — In `src/analysis/backtest_strategies.py`, find the line with `signal_data.get('reversion_second', 0)` (around line 81) and change it to `signal_data.get('entry_second', signal_data.get('reversion_second', 0))`. This makes the bridge strategy-agnostic: S2 uses `entry_second`, S1 uses `reversion_second`, and the fallback chain handles both. **Important:** S1's signal_data does NOT currently include `entry_second` — it uses `reversion_second`. Do NOT modify S1. The fallback chain handles this correctly.

## Must-Haves

- [ ] `shared/strategies/S2/` exists with `__init__.py`, `config.py`, `strategy.py`
- [ ] S2Config parameters match M4_CONFIG exactly (D005 — port as-is)
- [ ] S2Strategy.evaluate() is synchronous, pure, no imports from trading/analysis/core (D001, import isolation)
- [ ] S2Strategy.evaluate() returns Signal on calibrated volatility data, None on flat data
- [ ] Backtest adapter uses `signal_data.get('entry_second', signal_data.get('reversion_second', 0))` for entry second
- [ ] Registry `discover_strategies()` finds both S1 and S2
- [ ] `verify_s01.py` and `verify_s02.py` still pass (no regressions)

## Verification

- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; r = discover_strategies(); assert 'S2' in r and 'S1' in r, r; print('OK:', sorted(r))"`
- `cd src && PYTHONPATH=. python3 -c "
import numpy as np
from shared.strategies.S2.strategy import S2Strategy
from shared.strategies.base import MarketSnapshot
s = S2Strategy()
# Build synthetic data that triggers S2: oscillating prices around 0.60 in the vol window
prices = np.full(60, 0.50)
# Set price at eval_second=30 to 0.60 (deviation >= 0.08)
prices[30] = 0.60
# Create volatility in window [20:31]: alternating 0.55/0.45
for i in range(20, 30):
    prices[i] = 0.55 if i % 2 == 0 else 0.45
prices[30] = 0.60
snap = MarketSnapshot(prices=prices, elapsed_seconds=60, metadata={})
sig = s.evaluate(snap)
assert sig is not None, 'S2 should fire'
assert sig.direction == 'Down', f'Expected Down, got {sig.direction}'
assert sig.strategy_id == 'S2'
print('S2 fires correctly')
"` — S2 evaluates correctly on synthetic data
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — S01 regression
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — S02 regression (after adapter fix)

## Observability Impact

- **New signals:** S2's `Signal.signal_data` dict includes `eval_second`, `spread`, `volatility`, `entry_second`, and `price_at_eval` — these are the primary diagnostic keys for understanding S2 signal decisions.
- **Inspection:** `discover_strategies()` now returns `{'S1': ..., 'S2': ...}`. The backtest adapter prints `[S2] Evaluating N markets → M trades` when running S2.
- **Failure state:** S2 `evaluate()` returns `None` silently on any guard failure. To diagnose, replay with a `MarketSnapshot` and step through guards: data length, NaN at eval_second, deviation < 0.08, spread out of range, volatility < 0.05.
- **Backtest adapter change:** `entry_second` fallback chain (`entry_second` → `reversion_second` → `0`) is transparent — no new logging, but mismatched entry seconds would show as wrong `second_entered` in trade objects.

## Inputs

- `src/shared/strategies/S1/` — pattern to follow for file structure and class hierarchy
- `src/shared/strategies/base.py` — BaseStrategy, StrategyConfig, MarketSnapshot, Signal definitions
- `src/shared/strategies/registry.py` — auto-discovers strategy directories (no changes needed)
- `src/trading/strategies.py` — source of M4 volatility detection logic (~lines 260-400)
- `src/trading/constants.py` — M4_CONFIG parameter values
- `src/analysis/backtest_strategies.py` — line 81 needs the entry_second fix

## Expected Output

- `src/shared/strategies/S2/__init__.py` — empty file
- `src/shared/strategies/S2/config.py` — S2Config dataclass + get_default_config()
- `src/shared/strategies/S2/strategy.py` — S2Strategy(BaseStrategy) with evaluate()
- `src/analysis/backtest_strategies.py` — one-line fix to Signal→Trade bridge for generic entry_second
