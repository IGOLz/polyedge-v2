# S03: Implement all strategies — UAT

**Milestone:** M003
**Written:** 2026-03-18

## UAT Type

- **UAT mode:** artifact-driven
- **Why this mode is sufficient:** All strategies are pure functions that deterministically map MarketSnapshot → Signal|None. Verification script tests all strategies against synthetic market patterns and confirms correct behavior. No runtime components (servers, databases, UI) are involved in strategy evaluation. Full backtests against historical data deferred to S04 or user verification (worktree DB is empty per S02 forward intelligence).

## Preconditions

1. Working directory is `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003`
2. Python 3.x available with numpy installed
3. PYTHONPATH includes `src/` directory for imports
4. All 7 strategy folders (S1-S7) exist with config.py and strategy.py modules
5. Verification script exists at `scripts/verify_s03_strategies.sh`

## Smoke Test

Run the comprehensive verification script:

```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_s03_strategies.sh
```

**Expected:** Exit code 0 with "All S03 verification checks passed" message and no ✗ failures.

## Test Cases

### 1. All strategies import successfully

1. Navigate to worktree: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003`
2. Run verification script: `bash scripts/verify_s03_strategies.sh`
3. **Expected:** Check 1 shows "✓ S1 imports successfully" through "✓ S7 imports successfully" with no import errors

### 2. All strategies instantiate with correct metadata

1. Run verification script (same as above)
2. **Expected:** Check 2 shows all 7 strategies instantiated with correct strategy_id (S1-S7) and strategy_name (S1_calibration, S2_momentum, S3_reversion, S4_volatility, S5_time_phase, S6_streak, S7_composite)

### 3. All strategies have meaningful parameter grids

1. Run verification script
2. **Expected:** Check 3 shows:
   - S1: 5 parameters, 108 combinations
   - S2: 4 parameters, 72 combinations
   - S3: 4 parameters, 144 combinations
   - S4: 5 parameters, 108 combinations
   - S5: 5 parameters, 108 combinations
   - S6: 4 parameters, 72 combinations
   - S7: 7 parameters, 192 combinations

### 4. All strategies handle synthetic market patterns

1. Run verification script
2. **Expected:** Check 4 shows all 7 strategies handled 4 patterns (spike, flat, nan_heavy, extreme) without crashing
3. Verify no Python exceptions or traceback output

### 5. Returned signals have correct structure

1. Run verification script
2. **Expected:** Check 5 shows:
   - S1 signal structure valid (direction=Up, entry_second=30) — S1 triggers on test pattern
   - S2-S7 show "○ returned None (valid if conditions not met)" — these strategies don't trigger on the spike pattern used in Check 5, which is valid behavior

### 6. All strategies handle insufficient data gracefully

1. Run verification script
2. **Expected:** Check 6 shows all 7 strategies "handled sparse data gracefully (returned None)" with no crashes

### 7. Registry discovers all strategies

1. Navigate to worktree: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run registry check:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.registry import discover_strategies
   strategies = discover_strategies()
   print(f"Discovered {len(strategies)} strategies:")
   for sid in sorted(strategies.keys()):
       print(f"  {sid}")
   PYEOF
   ```
3. **Expected:** Output shows "Discovered 8 strategies:" with S1, S2, S3, S4, S5, S6, S7, TEMPLATE

### 8. S1 (Calibration) detects mispricing correctly

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S1.config import get_default_config
   from shared.strategies.S1.strategy import S1Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S1Strategy(cfg)
   
   # Create market with low price (0.42) suggesting Up opportunity
   prices = np.full(300, 0.42)
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Entry second: {sig.signal_data.get('entry_second') if sig else None}")
   print(f"Deviation: {sig.signal_data.get('deviation') if sig else None}")
   PYEOF
   ```
3. **Expected:** 
   - Signal direction: Up (price 0.42 < 0.45 → bet Up)
   - Entry price: 0.42 (clamped to [0.01, 0.99])
   - Entry second: 30-90 (within eval window)
   - Deviation: ≥ 0.08 (price deviation from 0.50)

### 9. S2 (Momentum) detects velocity correctly

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S2Strategy(cfg)
   
   # Create strong momentum pattern (0.30 at 30s → 0.95 at 60s)
   prices = np.linspace(0.30, 0.95, 300)
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Velocity: {sig.signal_data.get('velocity') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Down (strong upward momentum → fade it)
   - Entry price: ≈0.95 (current price at eval window end)
   - Velocity: ≈0.0217 (65 points over 30 seconds = ~0.02/s)

### 10. S3 (Mean Reversion) detects spike + reversion correctly

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S3.config import get_default_config
   from shared.strategies.S3.strategy import S3Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S3Strategy(cfg)
   
   # Create spike (0.50 → 0.85 at 20s) + reversion (0.85 → 0.70 at 90s)
   prices = np.full(300, 0.50)
   prices[20:60] = 0.85  # spike
   prices[60:120] = 0.70  # reversion
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Spike direction: {sig.signal_data.get('spike_direction') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Down (Up spike after reversion → fade it)
   - Entry price: ≈0.70 (price after reversion)
   - Spike direction: 'Up' (detected upward spike)

### 11. S4 (Volatility Regime) detects high vol + extreme price

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S4.config import get_default_config
   from shared.strategies.S4.strategy import S4Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S4Strategy(cfg)
   
   # Create high volatility pattern (swinging 0.20 ↔ 0.80) with current extreme low
   prices = np.tile([0.20, 0.80], 150)  # alternating extremes
   prices[-30:] = 0.20  # end at extreme low
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Volatility: {sig.signal_data.get('volatility') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Up (extreme low price + high vol → bet Up)
   - Entry price: 0.20
   - Volatility: ≥0.05 (high std dev from swinging pattern)

### 12. S5 (Time-Phase) filters by time window and hour

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S5.config import get_default_config
   from shared.strategies.S5.strategy import S5Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S5Strategy(cfg)
   
   # Create market with price 0.52 in entry window (60-120s), hour 14
   prices = np.full(300, 0.52)
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Hour: {sig.signal_data.get('hour') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Down (price 0.52 > 0.50 → bet toward middle)
   - Entry price: 0.52
   - Hour: 14 (passed hour filter if allowed_hours includes 14 or is None)

### 13. S6 (Streak) detects consecutive same-direction moves

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S6.config import get_default_config
   from shared.strategies.S6.strategy import S6Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   cfg.window_size = 15
   cfg.streak_length = 3
   cfg.min_move_threshold = 0.02
   s = S6Strategy(cfg)
   
   # Create 4 consecutive rising windows (15s each, 0.40 → 0.44 → 0.48 → 0.52 → 0.56)
   prices = np.concatenate([
       np.linspace(0.40, 0.44, 15),  # window 1: rising
       np.linspace(0.44, 0.48, 15),  # window 2: rising
       np.linspace(0.48, 0.52, 15),  # window 3: rising
       np.linspace(0.52, 0.56, 15),  # window 4: rising
       np.full(240, 0.56),           # rest of market
   ])
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Entry price: {sig.entry_price if sig else None}")
   print(f"Streak length: {sig.signal_data.get('streak_length') if sig else None}")
   print(f"Streak direction: {sig.signal_data.get('streak_direction') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Down (rising streak → fade it)
   - Entry price: ≈0.56 (price at window 5 start)
   - Streak length: ≥3 (detected consecutive rising windows)
   - Streak direction: 'up'

### 14. S7 (Composite) requires min_agreement for entry

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test with multiple patterns agreeing:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S7.config import get_default_config
   from shared.strategies.S7.strategy import S7Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   cfg.min_agreement = 2
   cfg.calibration_enabled = True
   cfg.momentum_enabled = True
   cfg.volatility_enabled = True
   s = S7Strategy(cfg)
   
   # Create pattern that triggers multiple detections:
   # - Low price (0.35) → triggers calibration (bet Up)
   # - Rising momentum (0.20 → 0.40 over 30s) → triggers momentum (bet Down)
   # - High vol + extreme low → triggers volatility (bet Up)
   prices = np.full(300, 0.35)
   prices[:30] = np.linspace(0.20, 0.35, 30)  # early rising momentum
   prices[30:60] = np.tile([0.30, 0.40], 15)  # high volatility
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal direction: {sig.direction if sig else None}")
   print(f"Up votes: {sig.signal_data.get('up_votes') if sig else None}")
   print(f"Down votes: {sig.signal_data.get('down_votes') if sig else None}")
   print(f"Total detections: {sig.signal_data.get('detections') if sig else None}")
   PYEOF
   ```
3. **Expected:**
   - Signal direction: Up or Down (whichever direction has ≥2 votes)
   - Up votes + Down votes ≥ 2 (multiple patterns triggered)
   - Total detections = up_votes + down_votes

## Edge Cases

### Sparse data (insufficient ticks)

1. Navigate to src: `cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003/src`
2. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S1.config import get_default_config
   from shared.strategies.S1.strategy import S1Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S1Strategy(cfg)
   
   # Create sparse data: only 5 valid prices in 300s window
   prices = np.full(300, np.nan)
   prices[0] = 0.50
   prices[60] = 0.52
   prices[120] = 0.48
   prices[180] = 0.51
   prices[240] = 0.49
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal: {sig}")  # Should be None
   PYEOF
   ```
3. **Expected:** Signal: None (insufficient data, strategy returns None gracefully without crashing)

### All NaN prices

1. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S2.config import get_default_config
   from shared.strategies.S2.strategy import S2Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S2Strategy(cfg)
   
   prices = np.full(300, np.nan)
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal: {sig}")  # Should be None
   PYEOF
   ```
3. **Expected:** Signal: None (no valid data, returns None without crashing)

### Flat prices (no movement)

1. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S6.config import get_default_config
   from shared.strategies.S6.strategy import S6Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   s = S6Strategy(cfg)
   
   prices = np.full(300, 0.50)  # all same price
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal: {sig}")  # Should be None (no streak detected)
   PYEOF
   ```
3. **Expected:** Signal: None (no price movement → no streak detected → returns None)

### Only 1 pattern triggers in S7 with min_agreement=2

1. Run test:
   ```bash
   PYTHONPATH=. python3 << 'PYEOF'
   from shared.strategies.S7.config import get_default_config
   from shared.strategies.S7.strategy import S7Strategy
   from shared.strategies.base import MarketSnapshot
   import numpy as np
   
   cfg = get_default_config()
   cfg.min_agreement = 2
   cfg.calibration_enabled = True
   cfg.momentum_enabled = False
   cfg.volatility_enabled = False
   s = S7Strategy(cfg)
   
   # Create pattern that triggers only calibration
   prices = np.full(300, 0.35)
   snap = MarketSnapshot('test', 'btc_5m', prices, 300, 300, {'hour': 14})
   sig = s.evaluate(snap)
   
   print(f"Signal: {sig}")  # Should be None (only 1 vote but min_agreement=2)
   PYEOF
   ```
3. **Expected:** Signal: None (only 1 pattern triggered but min_agreement requires 2 → correctly returns None)

## Failure Signals

- **✗ symbol in verification script output** — One or more checks failed
- **Non-zero exit code from verification script** — At least one strategy failed a check
- **Python exceptions/tracebacks** — Strategy crashed on synthetic data (should return None instead)
- **Import errors** — Strategy module missing or has syntax errors
- **Missing entry_second in signal_data** — Signal structure invalid
- **Entry price outside [0.01, 0.99]** — Clamping logic not applied
- **Registry discovers < 7 strategies** — Strategy not properly registered or folder structure wrong

## Requirements Proved By This UAT

- **R014** (Each strategy is a self-contained folder with config, evaluate(), and param grid) — Tests 1-7 prove all 7 strategies have functional configs, evaluate() methods, and parameter grids
- **R020** (Strategies cover major viable approaches for 5-min crypto up/down prediction markets) — Tests 8-14 prove 7 distinct strategy families are implemented with real detection logic
- **R021** (Strategies work across all collected assets) — All strategies use MarketSnapshot which is asset-agnostic; no asset-specific logic (though full verification against all assets deferred to S04/user backtests)

## Not Proven By This UAT

- **Strategy profitability on real historical data** — All tests use synthetic market patterns. Actual performance metrics (Sharpe, Sortino, win rate, profit factor) deferred to S04 or user backtest runs against real DB data.
- **Parameter optimization results** — UAT verifies parameter grids exist but does not run optimizer to find profitable parameter combinations. Deferred to S04/user evaluation.
- **Integration with backtest runner** — UAT verifies strategies work in isolation but does not run `python3 -m analysis.backtest_strategies` against real DB. Deferred to S04 verification or user runs.
- **Engine fee/slippage integration** — S02 verified engine dynamics separately; S03 UAT assumes engine integration works correctly and focuses solely on strategy signal generation.

## Notes for Tester

1. **None is a valid return value:** Strategies returning None means "no entry opportunity detected" or "insufficient data." This is correct behavior, not a failure. Most strategies will return None on most synthetic patterns because those patterns don't meet their specific detection thresholds.

2. **Parameter grid sizes vary:** S2 and S6 have 72 combinations (simpler strategies), S7 has 192 combinations (ensemble configuration space), others have 108-144. This is intentional — more complex strategies need larger grids.

3. **S7 inline duplication is documented limitation:** S7 duplicates logic from S1/S2/S4 inline due to pure function contract. This is architecturally necessary and documented in code/summary. Not a bug.

4. **S6 is simplified intra-market version:** S6 detects consecutive same-direction moves within a single market, not cross-market outcome streaks. This is documented limitation due to pure function contract constraints.

5. **Database not required for UAT:** All verification uses synthetic data. Real DB backtests are user verification phase, not S03 delivery requirement.

6. **Expected verification runtime:** Full verification script takes ~2 seconds. Individual strategy tests take <1 second each.
