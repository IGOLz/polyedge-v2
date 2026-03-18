# T02: Implement S4 (Volatility Regime), S5 (Time-Phase Entry)

## Description

Implement simplified standalone versions of volatility regime and time-phase entry strategies. These have partial references in backtest modules but need adaptation to work within the shared strategy framework's pure function constraints.

**S4 (Volatility Regime):** Calculate rolling standard deviation over a lookback window at a specific evaluation second. Enter contrarian when volatility is high (≥ threshold) AND price is extreme (≥0.70 or ≤0.30). High volatility + extreme price suggests overreaction — fade it.

**S5 (Time-Phase Entry):** Filter entry by elapsed time window (early/mid/late market) and optional hour-of-day constraints. Enter when current time falls within allowed window and price is in target range. Exploits patterns where certain time phases have better entry success.

Both strategies need the `_get_price()` helper for NaN-aware lookups and meaningful parameter grids.

## Steps

1. **Implement S4 Volatility Regime strategy**
   - Add `_get_price` helper to `src/shared/strategies/S4/strategy.py`
   - Edit `src/shared/strategies/S4/config.py`:
     - Replace example_* fields with: `lookback_window: int = 60`, `vol_threshold: float = 0.08`, `eval_second: int = 120`, `extreme_price_low: float = 0.30`, `extreme_price_high: float = 0.70`
     - Update `get_param_grid()` to return: `{"lookback_window": [30, 60, 90], "vol_threshold": [0.05, 0.08, 0.10], "eval_second": [60, 120, 180], "extreme_price_low": [0.25, 0.30], "extreme_price_high": [0.70, 0.75]}`
   - Edit `src/shared/strategies/S4/strategy.py`:
     - In `evaluate()`:
       - Guard check: if `snapshot.elapsed_seconds < cfg.eval_second`, return None
       - Collect prices from `(eval_second - lookback_window)` to `eval_second`
       - Build array of valid (non-NaN) prices in window
       - If < 10 valid prices, return None (insufficient data for volatility calculation)
       - Calculate std_dev = `np.std(valid_prices)`
       - Get current_price at eval_second via `_get_price(prices, cfg.eval_second)`
       - If std_dev ≥ vol_threshold AND current_price ≤ extreme_price_low, enter Up (price is too low, fade it)
       - If std_dev ≥ vol_threshold AND current_price ≥ extreme_price_high, enter Down (price is too high, fade it)
       - Otherwise return None
       - Populate signal_data={'entry_second': cfg.eval_second, 'volatility': std_dev, 'current_price': current_price}

2. **Implement S5 Time-Phase Entry strategy**
   - Add `_get_price` helper to `src/shared/strategies/S5/strategy.py`
   - Edit `src/shared/strategies/S5/config.py`:
     - Replace example_* fields with: `entry_window_start: int = 60`, `entry_window_end: int = 180`, `allowed_hours: list[int] | None = None`, `price_range_low: float = 0.45`, `price_range_high: float = 0.55`
     - Update `get_param_grid()` to return: `{"entry_window_start": [30, 60, 90], "entry_window_end": [120, 180, 240], "allowed_hours": [None, [10,11,12,13,14,15], [14,15,16,17,18]], "price_range_low": [0.40, 0.45], "price_range_high": [0.55, 0.60]}`
   - Edit `src/shared/strategies/S5/strategy.py`:
     - In `evaluate()`:
       - Scan elapsed seconds from entry_window_start to entry_window_end
       - For each second in window:
         - Check hour filter: if `cfg.allowed_hours is not None` and `snapshot.metadata['hour'] not in cfg.allowed_hours`, skip this second
         - Get price via `_get_price(prices, sec)`
         - If price is in range [price_range_low, price_range_high]:
           - Determine direction: if price < 0.50, enter Up; if price > 0.50, enter Down (bet toward middle)
           - Return Signal with entry_second=sec
       - Return None if no valid entry found in window

3. **Handle edge cases**
   - S4 must handle sparse data: if < 10 valid prices in lookback window, return None rather than calculate std_dev on tiny sample
   - S4 must handle flat prices: std_dev = 0 → no volatility → return None (volatility condition not met)
   - S5 must handle empty allowed_hours list: treat as no hour filter (all hours allowed)
   - S5 must handle case where entry_window_end > total_seconds: clamp scan range to available data
   - Both strategies must clamp entry_price to [0.01, 0.99]

4. **Spot-check both strategies**
   - For S4:
     - Create synthetic data with high volatility (prices swinging 0.30 → 0.70 → 0.30)
     - Set eval_second = 120, expect signal when current price is extreme AND volatility high
   - For S5:
     - Create synthetic data with price = 0.52 at second 90
     - Set entry_window = [60, 120], allowed_hours = None, price_range = [0.45, 0.55]
     - Expect signal at second 90 with direction='Down' (price > 0.50, bet toward middle)
   - Verify parameter grids return 10-40 combinations each

## Must-Haves

- S4 config has: lookback_window, vol_threshold, eval_second, extreme_price_low, extreme_price_high
- S4 evaluate() calculates rolling std dev and enters contrarian when volatility high + price extreme
- S4 param grid has 3×3×3×2×2 = 108 combinations
- S4 returns None for insufficient data (< 10 valid prices in window)
- S5 config has: entry_window_start, entry_window_end, allowed_hours, price_range_low, price_range_high
- S5 evaluate() scans time window, filters by hour (if specified), enters when price in range
- S5 param grid has 3×3×3×2×2 = 108 combinations
- Both strategies use `_get_price()` helper
- Both strategies clamp entry_price to [0.01, 0.99]
- Both populate signal_data['entry_second']

## Verification

Run this Python code in `src/` directory with `PYTHONPATH=.`:

```python
import sys
import numpy as np
from shared.strategies.base import MarketSnapshot

strategies = ['S4', 'S5']
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
        
        # Synthetic evaluation
        if sid == 'S4':
            # High volatility pattern
            prices = np.full(300, 0.50)
            for i in range(60, 120, 10):
                prices[i] = 0.70 if (i // 10) % 2 == 0 else 0.30
            snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
        else:  # S5
            # Price in range at specific time
            prices = np.full(300, 0.50)
            prices[90] = 0.52
            snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
        
        sig = s.evaluate(snap)
        
        # Verify signal structure if returned
        if sig is not None:
            if sig.direction not in ['Up', 'Down']:
                failures.append(f"{sid}: invalid direction {sig.direction}")
            if 'entry_second' not in sig.signal_data:
                failures.append(f"{sid}: missing entry_second in signal_data")
            if not (0.01 <= sig.entry_price <= 0.99):
                failures.append(f"{sid}: entry_price {sig.entry_price} out of bounds")
        
        # Test edge case: insufficient data
        sparse_prices = np.full(300, np.nan)
        sparse_prices[50] = 0.60
        sparse_snap = MarketSnapshot('test', 'btc_5m', sparse_prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
        sig_sparse = s.evaluate(sparse_snap)
        # Should return None for insufficient data, not crash
        
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

Expected: Exit code 0, both strategies pass.

## Inputs

- Scaffolding from S01:
  - `src/shared/strategies/S4/config.py`, `src/shared/strategies/S4/strategy.py`
  - `src/shared/strategies/S5/config.py`, `src/shared/strategies/S5/strategy.py`
- Base classes: `src/shared/strategies/base.py`
- Reference patterns from:
  - `src/analysis/backtest/module_4_volatility.py` (read-only, for volatility calculation approach)
  - `src/analysis/backtest/module_5_time_filters.py` (read-only, for time-based filtering patterns)

## Expected Output

- S4 has real volatility regime detection with rolling std dev calculation
- S5 has real time-phase entry filtering with hour-of-day support
- Both have meaningful parameter grids with 10-50+ combinations
- Both handle edge cases gracefully (sparse data, flat prices, out-of-window eval times)
- Spot-check verification passes for both

## Observability Impact

None — pure strategy implementations.

## Related Context

- Research doc section "Constraints" emphasizes handling NaN prices gracefully
- Research doc section "Common Pitfalls" warns about hardcoding market duration — use snapshot.total_seconds
