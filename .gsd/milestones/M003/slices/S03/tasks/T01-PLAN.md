# T01: Implement S1 (Calibration), S2 (Momentum), S3 (Mean Reversion)

## Description

Port detection logic from reference implementations (`strategy_calibration.py`, `strategy_momentum.py`, `module_3_mean_reversion.py`) into the shared strategy framework. These three strategies have complete reference implementations and are foundational patterns that prove the evaluate() → Signal → Trade pipeline works end-to-end with real detection logic.

**S1 (Calibration Mispricing):** Exploit systematic bias in 50/50 pricing. Enter contrarian when price deviates significantly from balanced (0.50). If price < 0.45, bet Up. If price > 0.55, bet Down. Evaluation window 30-60s.

**S2 (Early Momentum):** Detect directional velocity between 30s and 60s. Calculate velocity = (price_60s - price_30s) / 30s. Enter contrarian on strong momentum (if price rising fast, bet Down; if falling fast, bet Up).

**S3 (Mean Reversion):** Detect spike in first N seconds (price ≥ threshold), wait for reversion (price moves back ≥ reversal_pct from peak), then enter contrarian. Hold-to-resolution only (no mid-market exits for simplicity).

All three strategies need:
- Helper function `_get_price(prices, target_sec, tolerance=5)` for NaN-aware price lookup
- Real config parameters replacing example_* fields
- Meaningful parameter grids (2-5 values per parameter, 10-50 combinations)
- Entry price clamping to [0.01, 0.99]
- signal_data['entry_second'] population

## Steps

1. **Add _get_price helper to S1/strategy.py**
   - Function signature: `def _get_price(prices: np.ndarray, target_sec: int, tolerance: int = 5) -> float | None`
   - Logic: check target_sec first; if NaN, scan ±tolerance for nearest valid price; return None if no valid price found
   - Place before S1Strategy class definition

2. **Implement S1 Calibration strategy**
   - Edit `src/shared/strategies/S1/config.py`:
     - Replace example_* fields with: `entry_window_start: int = 30`, `entry_window_end: int = 60`, `price_low_threshold: float = 0.45`, `price_high_threshold: float = 0.55`, `min_deviation: float = 0.08`
     - Update `get_param_grid()` to return: `{"entry_window_start": [30, 45, 60], "entry_window_end": [60, 90, 120], "price_low_threshold": [0.40, 0.45], "price_high_threshold": [0.55, 0.60], "min_deviation": [0.05, 0.08, 0.10]}`
   - Edit `src/shared/strategies/S1/strategy.py`:
     - In `evaluate()`: scan prices between `entry_window_start` and `entry_window_end`
     - For each second in window, get price via `_get_price()`
     - If price < `price_low_threshold`, calculate deviation = 0.50 - price; if deviation ≥ min_deviation, enter Up
     - If price > `price_high_threshold`, calculate deviation = price - 0.50; if deviation ≥ min_deviation, enter Down
     - Clamp entry_price to [0.01, 0.99]
     - Return Signal with direction, entry_price, signal_data={'entry_second': sec, 'deviation': deviation}
     - Return None if no valid prices in window or no threshold breach

3. **Implement S2 Momentum strategy**
   - Add `_get_price` helper to `src/shared/strategies/S2/strategy.py`
   - Edit `src/shared/strategies/S2/config.py`:
     - Replace example_* fields with: `eval_window_start: int = 30`, `eval_window_end: int = 60`, `momentum_threshold: float = 0.03`, `tolerance: int = 10`
     - Update `get_param_grid()` to return: `{"eval_window_start": [25, 30, 35], "eval_window_end": [55, 60, 65], "momentum_threshold": [0.02, 0.03, 0.05, 0.08], "tolerance": [5, 10]}`
   - Edit `src/shared/strategies/S2/strategy.py`:
     - In `evaluate()`: get price_30s = `_get_price(prices, cfg.eval_window_start, cfg.tolerance)`
     - Get price_60s = `_get_price(prices, cfg.eval_window_end, cfg.tolerance)`
     - If either is None, return None
     - Calculate velocity = (price_60s - price_30s) / (cfg.eval_window_end - cfg.eval_window_start)
     - If velocity ≥ momentum_threshold, enter Down (contrarian); entry_price = 1.0 - price_60s
     - If velocity ≤ -momentum_threshold, enter Up (contrarian); entry_price = price_60s
     - Clamp entry_price
     - Return Signal with signal_data={'entry_second': cfg.eval_window_end, 'velocity': velocity, 'price_30s': price_30s, 'price_60s': price_60s}

4. **Implement S3 Mean Reversion strategy**
   - Add `_get_price` helper to `src/shared/strategies/S3/strategy.py`
   - Edit `src/shared/strategies/S3/config.py`:
     - Replace example_* fields with: `spike_threshold: float = 0.75`, `spike_lookback: int = 30`, `reversion_pct: float = 0.10`, `min_reversion_sec: int = 60`
     - Update `get_param_grid()` to return: `{"spike_threshold": [0.70, 0.75, 0.80, 0.85], "spike_lookback": [15, 30, 60], "reversion_pct": [0.05, 0.08, 0.10, 0.15], "min_reversion_sec": [30, 60, 120]}`
   - Edit `src/shared/strategies/S3/strategy.py`:
     - In `evaluate()`: implement two-phase detection:
       - **Phase 1 (Spike detection):** Scan first `spike_lookback` seconds for max/min price
       - Get all valid (non-NaN) prices in window
       - Check Up spike: max_price ≥ spike_threshold → spike_dir='Up', peak_sec, peak_price
       - Check Down spike: min_price ≤ (1.0 - spike_threshold) → spike_dir='Down', peak_sec, peak_price
       - If no spike, return None
       - **Phase 2 (Reversion wait):** From peak_sec+1 to peak_sec+min_reversion_sec, scan for reversion
       - If spike_dir='Up': wait for price to drop ≥ reversion_pct from peak → enter Down
       - If spike_dir='Down': wait for price to rise ≥ reversion_pct from trough → enter Up
       - Calculate entry_price based on current UP price at reversion second
       - Return Signal with signal_data={'entry_second': reversion_sec, 'spike_direction': spike_dir, 'peak_second': peak_sec, 'peak_price': peak_price}
     - Return None if no reversion within min_reversion_sec window

5. **Spot-check all three strategies**
   - For each strategy S1, S2, S3:
     - Import and instantiate: `from shared.strategies.SN.config import get_default_config; from shared.strategies.SN.strategy import SNStrategy; cfg = get_default_config(); s = SNStrategy(cfg)`
     - Create synthetic MarketSnapshot with spike pattern: `prices = np.full(300, 0.50); prices[60] = 0.70`
     - Call evaluate: `sig = s.evaluate(MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14}))`
     - Verify: sig is None or has direction, entry_price, entry_second in signal_data
     - Check parameter grid: `grid = get_param_grid(); assert len(grid) >= 2 and all(len(v) >= 2 for v in grid.values())`

## Must-Haves

- `_get_price()` helper function in all three strategy.py files
- S1 config has: entry_window_start, entry_window_end, price_low_threshold, price_high_threshold, min_deviation
- S1 evaluate() detects price deviation from 0.50 and enters contrarian
- S1 param grid has 3×3×2×2×3 = 108 combinations (acceptable, can reduce if needed)
- S2 config has: eval_window_start, eval_window_end, momentum_threshold, tolerance
- S2 evaluate() calculates velocity between two time points and enters contrarian on strong momentum
- S2 param grid has 3×3×4×2 = 72 combinations
- S3 config has: spike_threshold, spike_lookback, reversion_pct, min_reversion_sec
- S3 evaluate() implements spike detection → reversion wait → contrarian entry
- S3 param grid has 4×3×4×3 = 144 combinations
- All three strategies clamp entry_price to [0.01, 0.99]
- All three populate signal_data['entry_second']
- All three return None for insufficient data (no crashes)

## Verification

Run this Python code in `src/` directory with `PYTHONPATH=.`:

```python
import sys
import numpy as np
from shared.strategies.base import MarketSnapshot

strategies = ['S1', 'S2', 'S3']
failures = []

for sid in strategies:
    try:
        # Import
        config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config', 'get_param_grid'])
        strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
        
        # Instantiate
        cfg = config_mod.get_default_config()
        strategy_cls = getattr(strategy_mod, f'{sid}Strategy')
        s = strategy_cls(cfg)
        
        # Param grid
        grid = config_mod.get_param_grid()
        if len(grid) < 2:
            failures.append(f"{sid}: param grid has < 2 parameters")
        if any(len(v) < 2 for v in grid.values()):
            failures.append(f"{sid}: param grid has parameter with < 2 values")
        
        # Synthetic evaluation (spike pattern)
        prices = np.full(300, 0.50)
        prices[60] = 0.75  # spike at 60s
        snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
        sig = s.evaluate(snap)
        
        # Verify signal structure
        if sig is not None:
            if sig.direction not in ['Up', 'Down']:
                failures.append(f"{sid}: invalid direction {sig.direction}")
            if 'entry_second' not in sig.signal_data:
                failures.append(f"{sid}: missing entry_second in signal_data")
            if not (0.01 <= sig.entry_price <= 0.99):
                failures.append(f"{sid}: entry_price {sig.entry_price} out of bounds")
        
        print(f"✓ {sid}: passed all checks")
        
    except Exception as e:
        failures.append(f"{sid}: {type(e).__name__}: {e}")
        print(f"✗ {sid}: {type(e).__name__}: {e}")

if failures:
    print(f"\n{len(failures)} failures:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print(f"\nAll {len(strategies)} strategies passed verification.")
    sys.exit(0)
```

Expected: Exit code 0, all strategies pass.

## Inputs

- Reference implementations:
  - `src/analysis/strategies/strategy_calibration.py` (read-only, for logic reference)
  - `src/analysis/strategies/strategy_momentum.py` (read-only, for logic reference)
  - `src/analysis/backtest/module_3_mean_reversion.py` (read-only, for logic reference)
- Scaffolding from S01:
  - `src/shared/strategies/S1/config.py`, `src/shared/strategies/S1/strategy.py`
  - `src/shared/strategies/S2/config.py`, `src/shared/strategies/S2/strategy.py`
  - `src/shared/strategies/S3/config.py`, `src/shared/strategies/S3/strategy.py`
- Base classes: `src/shared/strategies/base.py` (BaseStrategy, MarketSnapshot, Signal)

## Expected Output

- S1, S2, S3 have real `evaluate()` implementations that detect their respective patterns
- All three have meaningful parameter grids with 10-50+ combinations
- Spot-check verification passes for all three (imports work, evaluation doesn't crash, signals have correct structure)
- `_get_price()` helper is defined and used consistently across all three strategies

## Observability Impact

None — pure strategy implementations with no runtime state or external dependencies. All diagnostics are local (return values, parameter grids).

## Related Context

- Research doc section "Build Order" describes these three as foundational strategies with complete references
- Research doc section "MarketSnapshot data access" defines the _get_price() helper pattern
- Research doc section "Constraints" emphasizes pure function contract (no DB access, handle NaN gracefully)
