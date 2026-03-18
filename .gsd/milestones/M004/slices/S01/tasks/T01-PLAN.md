# T01: Add stop_loss and take_profit to all strategy param grids

## Description

Extend all 7 existing strategy `get_param_grid()` functions and TEMPLATE to include `stop_loss` and `take_profit` parameter ranges. Each strategy currently returns a dict with entry parameter lists producing 72-144 combinations. Adding SL/TP with 3 values each creates a 9× multiplier, keeping total combinations manageable (<1000 per strategy).

Per D012, SL/TP are absolute price thresholds (e.g., 0.40) not relative offsets. Per D013, ranges should be strategy-specific, tuned to each strategy's typical entry prices.

## Steps

1. **Update S1 (calibration mispricing) config.py:**
   - Entry prices typically 0.45-0.55 (low/high calibration bands)
   - Add to return dict: `"stop_loss": [0.35, 0.40, 0.45]`
   - Add to return dict: `"take_profit": [0.65, 0.70, 0.75]`
   - These ranges work for both Up and Down bets — engine will handle direction logic in S02

2. **Update S2 (momentum) config.py:**
   - Entry prices around 0.50 at momentum detection
   - Add: `"stop_loss": [0.40, 0.45, 0.50]`
   - Add: `"take_profit": [0.60, 0.65, 0.70]`

3. **Update S3 (mean reversion) config.py:**
   - Entry at spikes (0.75-0.85 for Down bets, 0.15-0.25 for Up bets)
   - Add: `"stop_loss": [0.15, 0.20, 0.25]` — these work for Up bets
   - Add: `"take_profit": [0.75, 0.80, 0.85]` — these work for Down bets
   - Note: S03 will skip invalid combos (e.g., SL > TP for Up bets)

4. **Update S4 (volatility regime) config.py:**
   - Entry prices vary by regime (0.45-0.55 typical)
   - Add: `"stop_loss": [0.35, 0.40, 0.45]`
   - Add: `"take_profit": [0.65, 0.70, 0.75]`

5. **Update S5 (time-phase) config.py:**
   - Entry prices 0.45-0.60 depending on phase
   - Add: `"stop_loss": [0.35, 0.40, 0.45]`
   - Add: `"take_profit": [0.65, 0.70, 0.75]`

6. **Update S6 (streak) config.py:**
   - Entry prices 0.40-0.60
   - Add: `"stop_loss": [0.30, 0.35, 0.40]`
   - Add: `"take_profit": [0.70, 0.75, 0.80]`

7. **Update S7 (composite ensemble) config.py:**
   - Combines signals, entry prices 0.45-0.60
   - Add: `"stop_loss": [0.35, 0.40, 0.45]`
   - Add: `"take_profit": [0.65, 0.70, 0.75]`

8. **Update TEMPLATE/config.py:**
   - Add example SL/TP keys with comments:
     ```python
     # Stop loss and take profit are absolute price thresholds (not relative offsets).
     # For a Down bet (shorting Up token), stop_loss should be higher than entry_price,
     # and take_profit should be lower. Engine handles direction logic.
     # Tune ranges based on your strategy's typical entry prices.
     "stop_loss": [0.35, 0.40, 0.45],
     "take_profit": [0.65, 0.70, 0.75],
     ```

9. **Test imports:**
   - Run quick import check: `cd src && python3 -c "from shared.strategies.S1.config import get_param_grid; print(get_param_grid().keys())"`
   - Verify 'stop_loss' and 'take_profit' appear in keys
   - Repeat for S2-S7

## Must-Haves

- All 7 strategies (S1-S7) have `stop_loss` and `take_profit` keys in `get_param_grid()` return dict
- Each key maps to a list of 3 float values
- Ranges are strategy-specific, tuned to typical entry prices
- TEMPLATE has example SL/TP keys with clear comments
- All config files import without errors

## Verification

```bash
cd src && python3 -c "
from shared.strategies.S1.config import get_param_grid as g1
from shared.strategies.S2.config import get_param_grid as g2
from shared.strategies.S3.config import get_param_grid as g3
from shared.strategies.S4.config import get_param_grid as g4
from shared.strategies.S5.config import get_param_grid as g5
from shared.strategies.S6.config import get_param_grid as g6
from shared.strategies.S7.config import get_param_grid as g7
from shared.strategies.TEMPLATE.config import get_param_grid as gt

for name, fn in [('S1', g1), ('S2', g2), ('S3', g3), ('S4', g4), ('S5', g5), ('S6', g6), ('S7', g7), ('TEMPLATE', gt)]:
    grid = fn()
    assert 'stop_loss' in grid, f'{name} missing stop_loss'
    assert 'take_profit' in grid, f'{name} missing take_profit'
    assert len(grid['stop_loss']) > 0, f'{name} stop_loss empty'
    assert len(grid['take_profit']) > 0, f'{name} take_profit empty'
    print(f'{name}: ✓')
"
```

Expected: All strategies print checkmark, no assertion errors.

## Inputs

From research:
- `src/shared/strategies/S1-S7/config.py` — existing `get_param_grid()` functions
- Entry price ranges per strategy from research doc
- D012 (absolute thresholds), D013 (strategy-specific ranges)

## Expected Output

Modified files:
- `src/shared/strategies/S1/config.py` — `get_param_grid()` includes SL/TP keys
- `src/shared/strategies/S2/config.py` — same
- `src/shared/strategies/S3/config.py` — same
- `src/shared/strategies/S4/config.py` — same
- `src/shared/strategies/S5/config.py` — same
- `src/shared/strategies/S6/config.py` — same
- `src/shared/strategies/S7/config.py` — same
- `src/shared/strategies/TEMPLATE/config.py` — example SL/TP with comments

All imports succeed, verification command passes.

## Observability Impact

**Signals Changed:**
- `get_param_grid()` return dict now includes `stop_loss` and `take_profit` keys across all strategies
- Grid search in S03 will see expanded parameter space (9× multiplier from 3 SL × 3 TP values)
- Future backtest runs will log SL/TP parameters in metadata for each strategy variant

**Inspection Method:**
- Import any strategy config and call `get_param_grid()` to see full parameter space
- Run `scripts/verify_m004_s01.py` for automated grid inspection across all strategies
- Check TEMPLATE/config.py for documented example of SL/TP declaration pattern

**Failure State Visibility:**
- Import error: Python traceback shows which config.py file has syntax/semantic error
- Missing keys: Verification script assertion fails with strategy name and missing key
- Empty lists: Verification script detects `len() == 0` and reports
- Malformed ranges: Type errors surface immediately at import time (e.g., string instead of float)

**Redaction Constraints:**
- None — parameter ranges are configuration metadata, not secrets
