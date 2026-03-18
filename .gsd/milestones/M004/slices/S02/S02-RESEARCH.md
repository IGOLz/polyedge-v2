# S02 — Stop Loss & Take Profit Engine — Research

**Date:** 2026-03-18
**Status:** Ready for planning

## Summary

S02 adds early exit simulation to the backtest engine. Currently, the engine only supports "hold to resolution" — trades are evaluated at market close with a binary win/loss outcome. S02 introduces **stop loss** and **take profit** logic: scan the price array second-by-second after entry, and exit early when price hits a configured threshold.

The core deliverable is a `simulate_sl_tp_exit()` function that takes a price array, entry conditions, and SL/TP thresholds, then returns the exit second/price/reason. The existing `Trade` dataclass gets a new `exit_reason` field to distinguish 'sl' / 'tp' / 'resolution' outcomes. The `make_trade()` function will call the simulator and use the result to populate the Trade object.

This is **straightforward work** following an established pattern. The legacy `strategy_momentum.py` already demonstrates stop loss scanning logic. We adapt the pattern to the new engine structure, handle both Up and Down directions with absolute price thresholds per D012, and write comprehensive unit tests with synthetic price data to prove correctness.

## Recommendation

Implement `simulate_sl_tp_exit()` as a new function in `analysis/backtest/engine.py` that:
- Takes: `prices` (numpy array), `entry_second`, `entry_price`, `direction` ('Up'/'Down'), `stop_loss` (absolute price), `take_profit` (absolute price)
- Returns: `(exit_second, exit_price, exit_reason)` tuple where exit_reason is 'sl', 'tp', or 'resolution'
- Scans prices from `entry_second + 1` to end of array, checking both SL and TP thresholds every second
- For **Up bets**: SL hits when `price <= stop_loss`, TP hits when `price >= take_profit`
- For **Down bets**: Swap logic (engine's responsibility per D012) — SL hits when `price >= 1.0 - stop_loss`, TP hits when `price <= 1.0 - take_profit`
- Handles NaN prices gracefully (skip to next second with valid price)
- Returns resolution exit if no threshold hit before market ends

Extend `Trade` dataclass with `exit_reason: str` field defaulting to 'resolution' for backward compatibility.

Update `make_trade()` to:
- Accept optional `stop_loss` and `take_profit` parameters (default None for backward compatibility)
- Call `simulate_sl_tp_exit()` when both SL and TP are provided
- Use returned exit_second/exit_price/exit_reason to populate Trade object
- Calculate PnL via existing `calculate_pnl_exit()` for early exits

Write unit tests in `src/tests/test_sl_tp_engine.py` with synthetic price arrays proving:
- Up bet with SL hit: price drops below threshold → exits with exit_reason='sl', correct PnL
- Up bet with TP hit: price rises above threshold → exits with exit_reason='tp', correct PnL
- Down bet with SL hit: price rises above inverted threshold → exit_reason='sl'
- Down bet with TP hit: price drops below inverted threshold → exit_reason='tp'
- No threshold hit → hold to resolution, exit_reason='resolution'
- NaN handling: skip invalid prices, exit when first valid threshold hit
- PnL calculation matches expected for all exit paths

## Implementation Landscape

### Key Files

- `src/analysis/backtest/engine.py` — Add `simulate_sl_tp_exit()` function and extend `Trade` dataclass with `exit_reason` field. Update `make_trade()` to call simulator when SL/TP provided.

- `src/tests/test_sl_tp_engine.py` — Create new test file with synthetic price arrays proving correctness of SL/TP logic for all combinations (Up/Down × SL/TP × hit/miss).

### Build Order

**1. Extend Trade dataclass first** — add `exit_reason: str = 'resolution'` field to Trade in engine.py. This unblocks the next steps and maintains backward compatibility (existing code doesn't need to change).

**2. Implement simulate_sl_tp_exit()** — write the core function that scans prices and returns early exit conditions. Start with Up bet logic (simpler), then add Down bet direction swapping. Handle NaN prices by skipping to next valid second.

**3. Integrate with make_trade()** — update `make_trade()` signature to accept `stop_loss=None, take_profit=None`. When both provided, call `simulate_sl_tp_exit()` and use returned values. When None, preserve existing hold-to-resolution behavior.

**4. Unit tests last** — write comprehensive tests proving all exit paths work correctly. Use synthetic numpy arrays with controlled price movements. Test fixtures should cover:
   - Up SL hit (price drops below stop_loss)
   - Up TP hit (price rises above take_profit)
   - Down SL hit (price rises above 1.0 - stop_loss)
   - Down TP hit (price drops below 1.0 - take_profit)
   - No hit (hold to resolution)
   - NaN handling
   - PnL correctness via `calculate_pnl_exit()`

### Verification Approach

**Contract verification:**
- Run `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v`
- All tests pass, proving SL/TP logic correct for all exit paths
- Trade dataclass has exit_reason field
- make_trade() accepts stop_loss/take_profit parameters

**Manual smoke test:**
```python
import numpy as np
from analysis.backtest.engine import simulate_sl_tp_exit

# Up bet, price drops to hit SL
prices = np.array([0.55, 0.53, 0.48, 0.45, 0.40, 0.38])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.55, 
    direction='Up', stop_loss=0.45, take_profit=0.70
)
assert exit_sec == 3  # first second where price <= 0.45
assert exit_price == 0.45
assert reason == 'sl'

# Up bet, price rises to hit TP
prices = np.array([0.55, 0.58, 0.62, 0.68, 0.72, 0.75])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.55,
    direction='Up', stop_loss=0.45, take_profit=0.70
)
assert exit_sec == 4  # first second where price >= 0.70
assert exit_price == 0.72
assert reason == 'tp'
```

## Constraints

- **Backward compatibility required:** Existing code calls `make_trade()` without SL/TP parameters. These must remain optional (default None) so M003 backtest results remain reproducible.

- **Direction handling is engine responsibility (D012):** Strategy configs declare SL/TP as absolute prices assuming Up bets. Engine must swap/invert thresholds for Down bets. Strategy authors should never have to think about direction.

- **NaN price handling:** Historical tick data has gaps. Simulator must skip NaN seconds and check the next valid price. Cannot assume contiguous price data.

- **PnL calculation must use existing functions:** `calculate_pnl_exit()` already handles mid-market exits with fee calculation. Reuse it for SL/TP exits — don't duplicate fee logic.

- **Tests directory doesn't exist yet:** Need to create `src/tests/` and add empty `__init__.py` for pytest discovery.

## Common Pitfalls

- **Off-by-one errors in second scanning** — Entry happens at `entry_second`, so simulator must start scanning at `entry_second + 1`. Entry price itself shouldn't trigger immediate SL/TP.

- **Down bet threshold inversion** — For Down bets, we're actually holding the "Down" token which has price `1.0 - up_price`. So SL/TP thresholds work on the inverted price space. Engine must handle this transparently. Reference the legacy `strategy_momentum.py` lines 127-131 for the pattern.

- **TP and SL both hit in same second** — If a price spike causes both thresholds to trigger simultaneously, prioritize **stop loss** (risk management over profit taking). This matches standard trading practice.

- **NaN at resolution** — If market ends with NaN price, fall back to final_outcome (1.0 for win, 0.0 for loss). The resolution always has a binary outcome even if tick data is missing.

- **Exit price vs threshold price** — When SL hits at second S with price P, exit_price should be the actual price P, not the threshold. This gives accurate PnL calculation. If P exactly equals threshold, that's fine — use P.

## Forward Intelligence for S03

**Grid search integration:** S03 will call `make_trade()` with `stop_loss` and `take_profit` parameters from the parameter grid. The interface must be clean:

```python
# S03 will generate combinations like:
for sl in [0.35, 0.40, 0.45]:
    for tp in [0.65, 0.70, 0.75]:
        trade = make_trade(
            market, second_entered, entry_price, direction,
            stop_loss=sl, take_profit=tp, slippage=0.0, base_rate=0.063
        )
```

Make sure `stop_loss` and `take_profit` are **keyword-only** after the existing positional args to avoid breaking existing calls.

**Performance consideration:** Scanning 300 seconds per trade isn't expensive (it's just numpy array indexing), but with 1000+ parameter combinations × 1000+ markets, the grid search will do millions of price scans. Keep `simulate_sl_tp_exit()` pure and fast — no logging inside the loop, no defensive copies of the prices array.

**Exit reason statistics:** S04 will aggregate trades by exit_reason to show how many trades hit SL vs TP vs resolution. Make sure exit_reason is a plain string ('sl', 'tp', 'resolution') that's easy to group by in pandas.
