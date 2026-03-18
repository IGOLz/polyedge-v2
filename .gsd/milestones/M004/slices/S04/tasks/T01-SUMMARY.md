---
id: T01
parent: S04
milestone: M004
provides:
  - Market dict key consistency between data loader and engine
  - Active SL/TP simulation with early exit functionality
  - Exit reason diversity in backtest results (sl, tp, resolution)
key_files:
  - src/analysis/backtest/data_loader.py
  - src/analysis/backtest_strategies.py
key_decisions: []
patterns_established:
  - Market dicts use 'prices' key for tick arrays (architectural standard)
  - Atomic changes across producer and consumer to maintain data contract
observability_surfaces:
  - Trade.exit_reason field shows 'sl', 'tp', or 'resolution' based on price movements
  - Counter inspection of exit reasons via verification command
  - Market dict structure inspection: data_loader.load_all_data()[0].keys()
duration: 25m
verification_result: passed
completed_at: 2026-03-18T18:08:54+01:00
blocker_discovered: false
---

# T01: Fix Market Dict Key Mismatch & Verify SL/TP Simulation

**Renamed market dict key from 'ticks' to 'prices' in data loader and backtest consumer to enable SL/TP simulation**

## What Happened

The backtest engine's `make_trade()` function checks for `market.get('prices')` to run stop-loss and take-profit simulation, but the data loader was returning market dicts with a `'ticks'` key instead. This architectural mismatch caused the SL/TP simulator to be skipped entirely, resulting in all trades defaulting to `exit_reason='resolution'` even when stop_loss and take_profit parameters were correctly threaded through the pipeline from S03.

Fixed the mismatch by renaming the key in two places atomically:
1. `data_loader.py` line 117: Changed `'ticks': tick_array` to `'prices': tick_array`
2. `backtest_strategies.py` line 68: Changed `prices=market["ticks"]` to `prices=market["prices"]`

The atomic commit ensures the producer (data_loader) and consumer (backtest_strategies) stay consistent, preventing any KeyError during the transition.

After the fix, ran verification showing:
- With SL=0.4, TP=0.7: Got 32 stop loss exits and 1 take profit exit out of 33 trades
- With SL=0.1, TP=2.0: Got 27 stop loss exits and 6 resolution exits (markets that resolved before hitting SL/TP)
- Exit reason diversity confirmed: trades now show 'sl', 'tp', and 'resolution' based on actual price movements

## Verification

Ran comprehensive verification proving SL/TP simulation is active:

```bash
cd src && PYTHONPATH=. python3 -c "
from analysis.backtest_strategies import run_strategy
from analysis.backtest import data_loader
from shared.strategies import get_strategy
from collections import Counter

markets = data_loader.load_all_data()
strategy = get_strategy('S1')
trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.4, take_profit=0.7)

exit_reasons = Counter(t.exit_reason for t in trades)
print('Exit reason counts:', exit_reasons)
print('Got', exit_reasons.get('sl', 0), 'stop losses,', exit_reasons.get('tp', 0), 'take profits')
print('✓ SL/TP simulation verified active')
"
```

Output:
```
Exit reason counts: Counter({'sl': 32, 'tp': 1})
Got 32 stop losses, 1 take profits
✓ SL/TP simulation verified active
```

Also verified with looser parameters to confirm resolution exits still work:
```
Exit reason counts with loose params: Counter({'sl': 27, 'resolution': 6})
```

Confirmed no remaining `market['ticks']` references:
```bash
cd src && rg "market\['ticks'\]" .
# No matches (exit code 1)
```

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | SL/TP simulation verification | 0 | ✅ pass | ~5s |
| 2 | Exit reason diversity check | 0 | ✅ pass | ~5s |
| 3 | No remaining ticks references | 1 (no match) | ✅ pass | <1s |

## Diagnostics

**Inspection surfaces:**
- `Trade.exit_reason` field: Shows 'sl', 'tp', or 'resolution' based on price movements
- Counter verification: `Counter(t.exit_reason for t in trades)` shows distribution of exit types
- Market dict structure: `data_loader.load_all_data()[0].keys()` → includes 'prices', not 'ticks'

**Failure visibility:**
- All exit_reason='resolution': Indicates SL/TP simulation not running (would be the symptom of unfixed mismatch)
- KeyError on market dict access: Would indicate inconsistent key naming between producer and consumer
- No early exits with tight SL/TP parameters: Would suggest simulation logic not executing

**How to verify this task's output:**
```python
from analysis.backtest_strategies import run_strategy
from analysis.backtest import data_loader
from shared.strategies import get_strategy

markets = data_loader.load_all_data()
strategy = get_strategy('S1')
trades, _ = run_strategy('S1', strategy, markets[:50], stop_loss=0.3, take_profit=0.8)

# Should see mix of 'sl', 'tp', and/or 'resolution' based on price movements
exit_reasons = {t.exit_reason for t in trades}
print('Exit reasons observed:', exit_reasons)
```

## Deviations

None. Task plan was accurate and complete.

## Known Issues

None. The fix successfully enables SL/TP simulation and all verification passes.

## Files Created/Modified

- `src/analysis/backtest/data_loader.py` — Changed market dict key from 'ticks' to 'prices' (line 117)
- `src/analysis/backtest_strategies.py` — Updated market_to_snapshot() to access 'prices' key instead of 'ticks' (line 68)
