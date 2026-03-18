# T03: Implement S6 (Streak/Sequence) simplified intra-market version

## Description

Implement a simplified streak detection strategy that works within the pure function contract (no cross-market state). The original streak strategy from `strategy_streak.py` tracks consecutive same-outcome markets across sequential markets (e.g., 3 BTC 5m markets all resolve Up → bet Down on the 4th). This requires state across market evaluations.

The simplified intra-market version detects consecutive same-direction price moves within a single market. Divide the elapsed time into fixed-size windows, calculate price direction for each window, count consecutive same-direction windows, and enter contrarian when streak length reaches threshold.

Example: If price rises in windows 1, 2, 3, 4 (streak of 4 rising windows), enter Down on window 5 (mean reversion bet).

## Steps

1. **Add _get_price helper to S6/strategy.py**
   - Same signature as T01/T02: `def _get_price(prices: np.ndarray, target_sec: int, tolerance: int = 5) -> float | None`

2. **Define streak detection algorithm**
   - Divide market into windows of size `window_size` seconds
   - For each window, calculate direction:
     - Get price at window start and window end via `_get_price()`
     - If end_price > start_price + `min_move_threshold`, direction = 'up'
     - If end_price < start_price - `min_move_threshold`, direction = 'down'
     - Otherwise direction = 'flat'
   - Scan windows from start to end, count consecutive same-direction (non-flat) windows
   - When streak_length ≥ threshold, enter contrarian on next window
   - Entry second = start of window where streak condition met
   - Direction = opposite of streak direction (if streak is 'up', enter Down)

3. **Implement S6 config**
   - Edit `src/shared/strategies/S6/config.py`:
     - Replace example_* fields with: `window_size: int = 15`, `streak_length: int = 3`, `min_move_threshold: float = 0.03`, `min_windows: int = 5`
     - Update `get_param_grid()` to return: `{"window_size": [10, 15, 20, 30], "streak_length": [3, 4, 5], "min_move_threshold": [0.02, 0.03, 0.05], "min_windows": [4, 5]}`
     - `min_windows` = minimum number of windows required before evaluating (need history to detect streaks)

4. **Implement S6 evaluate()**
   - Edit `src/shared/strategies/S6/strategy.py`:
     - In `evaluate()`:
       - Calculate num_windows = `total_seconds // window_size`
       - If num_windows < `cfg.min_windows`, return None (insufficient data)
       - Build window direction list:
         ```python
         directions = []
         for i in range(num_windows):
             start_sec = i * window_size
             end_sec = (i + 1) * window_size - 1
             start_price = _get_price(prices, start_sec)
             end_price = _get_price(prices, end_sec)
             if start_price is None or end_price is None:
                 directions.append('unknown')
                 continue
             delta = end_price - start_price
             if delta > cfg.min_move_threshold:
                 directions.append('up')
             elif delta < -cfg.min_move_threshold:
                 directions.append('down')
             else:
                 directions.append('flat')
         ```
       - Scan directions list for consecutive streaks:
         ```python
         current_streak = 0
         streak_direction = None
         for i, d in enumerate(directions):
             if d in ['up', 'down']:
                 if d == streak_direction:
                     current_streak += 1
                 else:
                     current_streak = 1
                     streak_direction = d
                 
                 if current_streak >= cfg.streak_length:
                     # Enter contrarian on next window
                     entry_second = (i + 1) * window_size
                     if entry_second >= total_seconds:
                         return None  # no room for entry after streak
                     entry_price = _get_price(prices, entry_second)
                     if entry_price is None:
                         return None
                     # Contrarian: if streak is 'up', bet Down
                     direction = 'Down' if streak_direction == 'up' else 'Up'
                     entry_price_final = (1.0 - entry_price) if direction == 'Down' else entry_price
                     entry_price_final = max(0.01, min(0.99, entry_price_final))
                     return Signal(
                         direction=direction,
                         strategy_name=cfg.strategy_name,
                         entry_price=entry_price_final,
                         signal_data={
                             'entry_second': entry_second,
                             'streak_direction': streak_direction,
                             'streak_length': current_streak,
                             'window_size': window_size,
                         }
                     )
             else:
                 # 'flat' or 'unknown' breaks the streak
                 current_streak = 0
                 streak_direction = None
         ```
       - Return None if no streak ≥ threshold found

5. **Document limitations in docstring**
   - Add to S6Strategy class docstring:
     ```
     Note: This is a simplified intra-market version that detects consecutive
     same-direction price moves within one market. The original streak strategy
     tracked consecutive same-outcome markets across sequential markets, which
     requires cross-market state and cannot be implemented within the pure
     function contract. True cross-market streak detection would require the
     backtest runner to track streaks and inject state via snapshot.metadata.
     ```

6. **Spot-check S6**
   - Create synthetic data with manufactured streak:
     ```python
     prices = np.full(300, 0.50)
     # Create 4 consecutive rising windows (15s each)
     for i in range(4):
         start = i * 15
         end = (i + 1) * 15
         prices[start:end] = 0.50 + (i + 1) * 0.05  # rising trend
     # At window 5 (second 60), strategy should enter Down (contrarian)
     ```
   - Instantiate S6 with default config (window_size=15, streak_length=3)
   - Call evaluate() on synthetic snapshot
   - Expect signal with direction='Down', entry_second=60

## Must-Haves

- S6 config has: window_size, streak_length, min_move_threshold, min_windows
- S6 param grid has 4×3×3×2 = 72 combinations
- S6 evaluate() divides market into windows, calculates direction per window, counts streaks
- S6 enters contrarian when streak_length ≥ threshold
- S6 returns None if insufficient windows (< min_windows)
- S6 returns None if streak detected but no valid entry price available
- Docstring documents this is simplified intra-market version, not cross-market streak
- `_get_price()` helper used for price lookups
- Entry price clamped to [0.01, 0.99]
- signal_data['entry_second'] populated

## Verification

Run this Python code in `src/` directory with `PYTHONPATH=.`:

```python
import sys
import numpy as np
from shared.strategies.base import MarketSnapshot
from shared.strategies.S6.config import get_default_config, get_param_grid
from shared.strategies.S6.strategy import S6Strategy

failures = []

try:
    # Instantiate
    cfg = get_default_config()
    s = S6Strategy(cfg)
    
    # Param grid
    grid = get_param_grid()
    if len(grid) < 3:
        failures.append("S6: param grid has < 3 parameters")
    
    # Synthetic streak pattern: 4 consecutive rising windows
    prices = np.full(300, 0.50)
    for i in range(4):
        start = i * 15
        end = (i + 1) * 15
        # Each window rises by 0.05
        prices[start:end] = 0.50 + (i + 1) * 0.05
    
    snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
    sig = s.evaluate(snap)
    
    # Should detect streak of 3-4 rising windows and enter Down
    if sig is None:
        failures.append("S6: expected signal for streak pattern, got None")
    elif sig.direction != 'Down':
        failures.append(f"S6: expected direction='Down' for rising streak, got {sig.direction}")
    elif 'entry_second' not in sig.signal_data:
        failures.append("S6: missing entry_second in signal_data")
    elif 'streak_length' not in sig.signal_data:
        failures.append("S6: missing streak_length in signal_data")
    
    # Test edge case: flat prices (no streaks)
    flat_prices = np.full(300, 0.50)
    flat_snap = MarketSnapshot('test', 'btc_5m', flat_prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
    sig_flat = s.evaluate(flat_snap)
    if sig_flat is not None:
        failures.append("S6: expected None for flat prices, got signal")
    
    # Test edge case: insufficient windows
    short_prices = np.full(60, 0.50)  # only 4 windows of 15s each
    short_snap = MarketSnapshot('test', 'btc_1m', short_prices, 60, 60, {'hour': 14, 'asset': 'BTC'})
    sig_short = s.evaluate(short_snap)
    # Should return None if min_windows = 5 (default)
    
    print("✓ S6: passed all checks")
    
except Exception as e:
    failures.append(f"S6: {type(e).__name__}: {e}")
    print(f"✗ S6: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

if failures:
    print(f"\n{len(failures)} failures:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nS6 strategy passed verification.")
    sys.exit(0)
```

Expected: Exit code 0, S6 passes.

## Inputs

- Scaffolding from S01: `src/shared/strategies/S6/config.py`, `src/shared/strategies/S6/strategy.py`
- Base classes: `src/shared/strategies/base.py`
- Reference pattern (read-only): `src/analysis/strategies/strategy_streak.py` (cross-market version, for conceptual understanding only)

## Expected Output

- S6 has real intra-market streak detection with windowed price direction analysis
- S6 has meaningful parameter grid with 50-100 combinations
- S6 handles edge cases: flat prices (no streaks), insufficient windows, missing prices
- Spot-check verification passes
- Docstring clearly documents this is simplified intra-market version

## Observability Impact

None — pure strategy implementation.

## Related Context

- Research doc section "Constraints" emphasizes pure function contract — no cross-market state allowed
- Research doc section "Open Risks" acknowledges streak strategy may produce too few trades (acceptable outcome)
- Research doc "Forward Intelligence" notes streak strategy is simplified and documents the limitation
