# T04: Implement S7 (Composite Ensemble) with inline multi-pattern detection

## Description

Implement the composite ensemble strategy that runs multiple detection patterns and returns a signal only when ≥ min_agreement strategies agree on direction. This is the most architecturally complex strategy — it proves that multiple detection patterns can coexist within one evaluate() function.

The shared evaluate() contract doesn't allow calling other strategies (no access to registry, pure function). Solution: duplicate core detection logic from 2-3 simple strategies inline. This isn't as clean as true composition but maintains the pure function contract.

**Detection patterns to inline:**
1. **Calibration** (from S1): Check if price deviates from 0.50
2. **Momentum** (from S2): Check if velocity between 30s-60s exceeds threshold
3. **Volatility** (from S4): Check if rolling std dev is high and price is extreme

Run all enabled patterns, collect signals (direction + optional confidence), and return Signal only if ≥ min_agreement patterns agree on direction.

## Steps

1. **Add _get_price helper to S7/strategy.py**
   - Same signature as previous tasks

2. **Define inline detection functions**
   - Add three private methods to S7Strategy class:
     - `_detect_calibration(snapshot: MarketSnapshot) -> tuple[str, float] | None` — returns ('Up'|'Down', confidence) or None
     - `_detect_momentum(snapshot: MarketSnapshot) -> tuple[str, float] | None`
     - `_detect_volatility(snapshot: MarketSnapshot) -> tuple[str, float] | None`
   - Each method implements simplified version of its corresponding strategy's core logic
   - Return format: (direction, confidence) where confidence is 0.0-1.0 (can be hardcoded as 1.0 initially)
   - Return None if detection conditions not met

3. **Implement S7 config**
   - Edit `src/shared/strategies/S7/config.py`:
     - Replace example_* fields with:
       ```python
       min_agreement: int = 2  # minimum strategies that must agree
       calibration_enabled: bool = True
       momentum_enabled: bool = True
       volatility_enabled: bool = True
       # Thresholds for each pattern
       calibration_deviation: float = 0.08
       calibration_eval_window: int = 60
       momentum_threshold: float = 0.03
       momentum_eval_start: int = 30
       momentum_eval_end: int = 60
       volatility_threshold: float = 0.08
       volatility_lookback: int = 60
       volatility_eval_sec: int = 120
       extreme_price_low: float = 0.30
       extreme_price_high: float = 0.70
       ```
     - Update `get_param_grid()` to return:
       ```python
       {
           "min_agreement": [2, 3],
           "calibration_enabled": [True, False],
           "momentum_enabled": [True, False],
           "volatility_enabled": [True, False],
           "calibration_deviation": [0.05, 0.08, 0.10],
           "momentum_threshold": [0.03, 0.05],
           "volatility_threshold": [0.08, 0.10],
       }
       ```
       This produces ~2 × 2 × 2 × 2 × 3 × 2 × 2 = 96 combinations

4. **Implement detection methods**
   - `_detect_calibration()`:
     ```python
     def _detect_calibration(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
         cfg = self.config
         if not cfg.calibration_enabled:
             return None
         prices = snapshot.prices
         # Scan window 0 to calibration_eval_window
         for sec in range(min(cfg.calibration_eval_window, snapshot.total_seconds)):
             price = _get_price(prices, sec)
             if price is None:
                 continue
             # If price < 0.50 - deviation, bet Up
             if price < (0.50 - cfg.calibration_deviation):
                 return ('Up', 1.0)
             # If price > 0.50 + deviation, bet Down
             if price > (0.50 + cfg.calibration_deviation):
                 return ('Down', 1.0)
         return None
     ```
   - `_detect_momentum()`:
     ```python
     def _detect_momentum(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
         cfg = self.config
         if not cfg.momentum_enabled:
             return None
         prices = snapshot.prices
         p30 = _get_price(prices, cfg.momentum_eval_start, tolerance=10)
         p60 = _get_price(prices, cfg.momentum_eval_end, tolerance=10)
         if p30 is None or p60 is None:
             return None
         velocity = (p60 - p30) / (cfg.momentum_eval_end - cfg.momentum_eval_start)
         if velocity >= cfg.momentum_threshold:
             return ('Down', 1.0)  # contrarian
         if velocity <= -cfg.momentum_threshold:
             return ('Up', 1.0)  # contrarian
         return None
     ```
   - `_detect_volatility()`:
     ```python
     def _detect_volatility(self, snapshot: MarketSnapshot) -> tuple[str, float] | None:
         cfg = self.config
         if not cfg.volatility_enabled:
             return None
         if snapshot.elapsed_seconds < cfg.volatility_eval_sec:
             return None
         prices = snapshot.prices
         window_start = max(0, cfg.volatility_eval_sec - cfg.volatility_lookback)
         valid_prices = []
         for sec in range(window_start, cfg.volatility_eval_sec):
             p = _get_price(prices, sec)
             if p is not None:
                 valid_prices.append(p)
         if len(valid_prices) < 10:
             return None
         std_dev = np.std(valid_prices)
         if std_dev < cfg.volatility_threshold:
             return None
         current_price = _get_price(prices, cfg.volatility_eval_sec)
         if current_price is None:
             return None
         if current_price <= cfg.extreme_price_low:
             return ('Up', 1.0)
         if current_price >= cfg.extreme_price_high:
             return ('Down', 1.0)
         return None
     ```

5. **Implement S7 evaluate() with voting logic**
   - Edit `src/shared/strategies/S7/strategy.py`:
     ```python
     def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
         cfg = self.config
         
         # Collect signals from all enabled patterns
         detections = []
         
         cal_result = self._detect_calibration(snapshot)
         if cal_result is not None:
             detections.append(cal_result)
         
         mom_result = self._detect_momentum(snapshot)
         if mom_result is not None:
             detections.append(mom_result)
         
         vol_result = self._detect_volatility(snapshot)
         if vol_result is not None:
             detections.append(vol_result)
         
         # Count votes by direction
         up_votes = sum(1 for d, _ in detections if d == 'Up')
         down_votes = sum(1 for d, _ in detections if d == 'Down')
         
         # Check if min_agreement met
         if up_votes >= cfg.min_agreement:
             direction = 'Up'
         elif down_votes >= cfg.min_agreement:
             direction = 'Down'
         else:
             return None  # no consensus
         
         # Calculate entry_second as median of enabled eval windows
         # Simplification: use momentum eval_end (60s) as representative entry point
         entry_second = cfg.momentum_eval_end
         entry_price = _get_price(snapshot.prices, entry_second)
         if entry_price is None:
             return None
         
         # Adjust for direction
         if direction == 'Down':
             entry_price = 1.0 - entry_price
         entry_price = max(0.01, min(0.99, entry_price))
         
         return Signal(
             direction=direction,
             strategy_name=cfg.strategy_name,
             entry_price=entry_price,
             signal_data={
                 'entry_second': entry_second,
                 'up_votes': up_votes,
                 'down_votes': down_votes,
                 'detections': len(detections),
             }
         )
     ```

6. **Document duplication in docstring**
   - Add to S7Strategy class docstring:
     ```
     Note: This strategy duplicates detection logic from S1 (calibration),
     S2 (momentum), and S4 (volatility) inline rather than calling those
     strategies. The pure function contract prevents accessing the registry
     or calling other strategies. If S1/S2/S4 logic changes, this strategy
     must be updated manually. A future refactoring could extract shared
     detection functions into a utility module.
     ```

7. **Spot-check S7**
   - Create synthetic data where 2+ patterns trigger:
     - Price at 30s = 0.45 (calibration: bet Up)
     - Price at 60s = 0.30 (momentum: velocity negative, bet Up)
     - High volatility + extreme price (volatility: bet Up)
   - Instantiate S7 with min_agreement=2, all patterns enabled
   - Call evaluate(), expect signal with direction='Up', up_votes=3

## Must-Haves

- S7 config has: min_agreement, calibration_enabled, momentum_enabled, volatility_enabled, plus thresholds for each pattern
- S7 param grid has ~50-100 combinations exploring ensemble configurations
- S7 has three private detection methods: _detect_calibration, _detect_momentum, _detect_volatility
- S7 evaluate() runs all enabled patterns, counts votes, returns Signal only if min_agreement met
- S7 returns None if consensus not reached
- Docstring documents inline duplication and manual sync requirement
- `_get_price()` helper used throughout
- Entry price clamped to [0.01, 0.99]
- signal_data contains voting details (up_votes, down_votes, detections count)

## Verification

Run this Python code in `src/` directory with `PYTHONPATH=.`:

```python
import sys
import numpy as np
from shared.strategies.base import MarketSnapshot
from shared.strategies.S7.config import get_default_config, get_param_grid
from shared.strategies.S7.strategy import S7Strategy

failures = []

try:
    # Instantiate
    cfg = get_default_config()
    s = S7Strategy(cfg)
    
    # Param grid
    grid = get_param_grid()
    if len(grid) < 3:
        failures.append("S7: param grid has < 3 parameters")
    
    # Synthetic data where multiple patterns trigger
    prices = np.full(300, 0.50)
    prices[30] = 0.40  # calibration: price < 0.50 - 0.08 → Up
    prices[60] = 0.35  # momentum: falling → Up (contrarian)
    # Add volatility by swinging prices
    for i in range(90, 120, 5):
        prices[i] = 0.70 if (i // 5) % 2 == 0 else 0.30
    prices[120] = 0.25  # extreme low → Up
    
    snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
    sig = s.evaluate(snap)
    
    # Should detect agreement (2+ patterns say Up)
    if sig is None:
        failures.append("S7: expected signal when 2+ patterns agree, got None")
    elif sig.direction != 'Up':
        failures.append(f"S7: expected direction='Up' for consensus pattern, got {sig.direction}")
    elif 'entry_second' not in sig.signal_data:
        failures.append("S7: missing entry_second in signal_data")
    elif 'up_votes' not in sig.signal_data or sig.signal_data['up_votes'] < 2:
        failures.append(f"S7: expected up_votes >= 2, got {sig.signal_data.get('up_votes')}")
    
    # Test edge case: only 1 pattern triggers (min_agreement=2 should fail)
    single_prices = np.full(300, 0.50)
    single_prices[30] = 0.40  # only calibration triggers
    single_snap = MarketSnapshot('test', 'btc_5m', single_prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
    sig_single = s.evaluate(single_snap)
    if sig_single is not None:
        failures.append("S7: expected None when only 1 pattern triggers (min_agreement=2), got signal")
    
    # Test edge case: disagreement (some say Up, some say Down)
    conflict_prices = np.full(300, 0.50)
    conflict_prices[30] = 0.40  # calibration: Up
    conflict_prices[60] = 0.65  # momentum: rising → Down (contrarian)
    conflict_snap = MarketSnapshot('test', 'btc_5m', conflict_prices, 300, 300, {'hour': 14, 'asset': 'BTC'})
    sig_conflict = s.evaluate(conflict_snap)
    # With min_agreement=2 and only 2 detections disagreeing, should return None
    
    print("✓ S7: passed all checks")
    
except Exception as e:
    failures.append(f"S7: {type(e).__name__}: {e}")
    print(f"✗ S7: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

if failures:
    print(f"\n{len(failures)} failures:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nS7 strategy passed verification.")
    sys.exit(0)
```

Expected: Exit code 0, S7 passes.

## Inputs

- Scaffolding from S01: `src/shared/strategies/S7/config.py`, `src/shared/strategies/S7/strategy.py`
- Base classes: `src/shared/strategies/base.py`
- Detection logic patterns from T01 (S1, S2) and T02 (S4) — for inline duplication reference

## Expected Output

- S7 has real composite ensemble logic with inline pattern detection
- S7 has meaningful parameter grid exploring ensemble configurations
- S7 correctly implements voting logic (min_agreement threshold)
- S7 handles edge cases: single detection (no consensus), disagreement between patterns
- Spot-check verification passes
- Docstring documents inline duplication and manual sync requirement

## Observability Impact

None — pure strategy implementation. The signal_data includes voting breakdown (up_votes, down_votes) which aids in understanding why the strategy entered.

## Related Context

- Research doc section "Build Order" lists S7 last because it depends on understanding patterns from S1-S6
- Research doc section "Composite ensemble may not add value" acknowledges this is a research risk — ensemble only helps if base strategies have uncorrelated errors
- Research doc section "Forward Intelligence" notes S7 duplicates logic from S1-S3 inline and should be refactored to true composition in future milestone
