# T03: Integration with make_trade() and comprehensive unit tests

**Description:** Wire the simulate_sl_tp_exit() function into the make_trade() flow so that trades created with stop loss and take profit parameters automatically use the early exit logic. Update make_trade() to accept optional SL/TP parameters, call the simulator when both are provided, and use the returned exit values to populate the Trade object. Write comprehensive unit tests covering all exit paths (Up/Down × SL/TP × hit/miss), NaN handling, edge cases, and PnL calculation correctness.

**Context from slice goal:** This task closes the loop on S02 by integrating the simulator with the trade creation workflow and proving correctness through exhaustive testing. The make_trade() signature must maintain backward compatibility (SL/TP optional, default None) so existing M003 backtest code continues working. Tests must cover the full matrix of scenarios to prove R025 (engine simulates SL/TP exits) and R031 (trades distinguish exit reasons) are satisfied.

**Estimated duration:** 1h

## Steps

1. **Update make_trade() signature** — In `src/analysis/backtest/engine.py`, modify the `make_trade()` function:
   - Add keyword-only parameters after existing positional args: `*, stop_loss=None, take_profit=None`
   - This ensures existing calls without SL/TP continue working (backward compatibility constraint from research)
   - Update docstring to document new parameters: "stop_loss/take_profit: Optional absolute price thresholds for early exit. If both provided, simulator scans prices and exits early when threshold hit."

2. **Add simulator integration logic** — Inside `make_trade()`, before the existing PnL calculation:
   - Check if both `stop_loss is not None and take_profit is not None`
   - If true, call `simulate_sl_tp_exit()` with market prices, entry conditions, and SL/TP thresholds:
     ```python
     if stop_loss is not None and take_profit is not None:
         exit_second, exit_price, exit_reason = simulate_sl_tp_exit(
             market.prices, second_entered, entry_price, direction,
             stop_loss, take_profit
         )
     else:
         # Existing hold-to-resolution logic
         exit_second = len(market.prices) - 1
         exit_price = market.prices[-1] if not np.isnan(market.prices[-1]) else (1.0 if direction == 'Up' else 0.0)
         exit_reason = 'resolution'
     ```
   - Replace existing exit logic references with the new exit_second/exit_price variables

3. **Update PnL calculation to use early exit values** — Modify the PnL calculation call:
   - If early exit occurred (exit_reason != 'resolution'), use `calculate_pnl_exit()` with exit_second and exit_price
   - The function already exists and handles mid-market exits with fees (research doc confirms we must reuse it, not duplicate fee logic)
   - Ensure Trade object instantiation uses the exit_reason from simulator

4. **Write unit tests for Up bet scenarios** — In `src/tests/test_sl_tp_engine.py`, implement test functions:
   - `test_up_bet_sl_hit()`: synthetic prices drop below SL → verify exit_reason='sl', correct exit_second/price, PnL < 0
   - `test_up_bet_tp_hit()`: synthetic prices rise above TP → verify exit_reason='tp', correct exit_second/price, PnL > 0
   - `test_up_bet_no_hit()`: prices stay between SL and TP → verify exit_reason='resolution', exit at market close

5. **Write unit tests for Down bet scenarios** — Add Down bet test functions:
   - `test_down_bet_sl_hit()`: prices rise above inverted SL threshold → exit_reason='sl', correct values
   - `test_down_bet_tp_hit()`: prices drop below inverted TP threshold → exit_reason='tp', correct values
   - `test_down_bet_no_hit()`: prices stay within safe range → exit_reason='resolution'

6. **Write edge case tests** — Add tests for special scenarios:
   - `test_nan_handling()`: price array with NaN values → simulator skips NaN seconds, exits at first valid threshold hit
   - `test_both_thresholds_same_second()`: price movement hits both SL and TP in one second → verify SL prioritized (exit_reason='sl')
   - `test_exit_at_boundary()`: threshold hit at first second after entry → verify exit_second = entry_second + 1
   - `test_all_nan_after_entry()`: all prices after entry are NaN → verify resolution exit with last valid price

7. **Write PnL correctness tests** — Add tests verifying PnL calculation via existing `calculate_pnl_exit()`:
   - `test_pnl_sl_exit()`: construct market with known prices, SL exit at specific second → verify PnL matches hand-calculated value with fees
   - `test_pnl_tp_exit()`: similar for TP exit → verify PnL calculation correct
   - Use the existing fee calculation logic (polymarket_dynamic_fee) to compute expected PnL, compare with actual Trade.pnl

8. **Implement synthetic market fixture** — Complete the fixture skeleton from T01:
   ```python
   @pytest.fixture
   def synthetic_market():
       """Create a MarketSnapshot with controlled price movement for testing."""
       def _make_market(prices: list[float], market_id: str = 'test_market'):
           return MarketSnapshot(
               market_id=market_id,
               question='Test Market',
               prices=np.array(prices),
               start_time=0,
               end_time=len(prices)
           )
       return _make_market
   ```

9. **Run full test suite** — Execute `cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v` and ensure all tests pass. Minimum 8 test cases covering the matrix of scenarios documented in slice verification requirements.

## Must-Haves

- `make_trade()` signature includes `*, stop_loss=None, take_profit=None` (keyword-only, optional)
- Function calls `simulate_sl_tp_exit()` when both SL/TP provided, uses returned exit values
- Backward compatibility: existing calls without SL/TP continue working (use hold-to-resolution logic)
- PnL calculation uses existing `calculate_pnl_exit()` function (no fee logic duplication)
- Trade object instantiation includes exit_reason from simulator
- Unit tests cover: Up SL hit, Up TP hit, Up no hit, Down SL hit, Down TP hit, Down no hit, NaN handling, both thresholds same second
- PnL correctness tests verify calculate_pnl_exit() integration
- All tests pass with exit code 0
- Test file has docstring explaining coverage (already in skeleton from T01)

## Verification

Run the full test suite:

```bash
cd src && PYTHONPATH=. python3 -m pytest tests/test_sl_tp_engine.py -v
```

Expected output shows all test functions pass:
```
tests/test_sl_tp_engine.py::test_up_bet_sl_hit PASSED
tests/test_sl_tp_engine.py::test_up_bet_tp_hit PASSED
tests/test_sl_tp_engine.py::test_up_bet_no_hit PASSED
tests/test_sl_tp_engine.py::test_down_bet_sl_hit PASSED
tests/test_sl_tp_engine.py::test_down_bet_tp_hit PASSED
tests/test_sl_tp_engine.py::test_down_bet_no_hit PASSED
tests/test_sl_tp_engine.py::test_nan_handling PASSED
tests/test_sl_tp_engine.py::test_both_thresholds_same_second PASSED
tests/test_sl_tp_engine.py::test_exit_at_boundary PASSED
tests/test_sl_tp_engine.py::test_all_nan_after_entry PASSED
tests/test_sl_tp_engine.py::test_pnl_sl_exit PASSED
tests/test_sl_tp_engine.py::test_pnl_tp_exit PASSED

============ 12 passed in X.XXs ============
```

Also verify backward compatibility manually:

```bash
cd src && python3 << 'EOF'
from analysis.backtest.engine import make_trade
from shared.types import MarketSnapshot
import numpy as np

# Create synthetic market
market = MarketSnapshot(
    market_id='test',
    question='Test',
    prices=np.array([0.50, 0.52, 0.48, 0.55, 0.60]),
    start_time=0,
    end_time=5
)

# Call make_trade WITHOUT SL/TP (backward compatibility check)
trade = make_trade(market, 0, 0.50, 'Up', slippage=0.0, base_rate=0.063)
assert trade.exit_reason == 'resolution', f"Expected 'resolution', got '{trade.exit_reason}'"
print('✓ Backward compatibility verified - make_trade() works without SL/TP')

# Call make_trade WITH SL/TP
trade_with_sl = make_trade(market, 0, 0.50, 'Up', slippage=0.0, base_rate=0.063, stop_loss=0.45, take_profit=0.58)
assert trade_with_sl.exit_reason in ['sl', 'tp', 'resolution'], f"Unexpected exit_reason: {trade_with_sl.exit_reason}"
print(f'✓ SL/TP integration verified - exit_reason={trade_with_sl.exit_reason}')
EOF
```

Both commands must succeed with exit code 0.

## Inputs

- `src/analysis/backtest/engine.py` with simulate_sl_tp_exit() function (from T02)
- `src/analysis/backtest/engine.py` with Trade dataclass extended with exit_reason (from T01)
- `src/tests/test_sl_tp_engine.py` skeleton (from T01)
- Existing `calculate_pnl_exit()` function in engine.py for PnL calculation
- Existing `polymarket_dynamic_fee()` function for fee calculation (used in test verification)
- Research doc guidance on test coverage requirements

## Expected Output

**Files modified:**

1. **`src/analysis/backtest/engine.py`** — make_trade() function updated:
   ```python
   def make_trade(
       market: MarketSnapshot,
       second_entered: int,
       entry_price: float,
       direction: str,
       slippage: float,
       base_rate: float,
       *,
       stop_loss: Optional[float] = None,
       take_profit: Optional[float] = None
   ) -> Trade:
       """Create a Trade object with PnL calculation.
       
       Args:
           market: MarketSnapshot with price data
           second_entered: Second when trade entered
           entry_price: Price at entry
           direction: 'Up' or 'Down'
           slippage: Slippage penalty to apply to entry price
           base_rate: Base fee rate for Polymarket dynamic fee calculation
           stop_loss: Optional absolute price threshold for stop loss exit
           take_profit: Optional absolute price threshold for take profit exit
       
       Returns:
           Trade object with PnL, exit conditions, and exit_reason
       """
       # Apply slippage
       adjusted_entry_price = entry_price * (1 - slippage) if direction == 'Up' else entry_price * (1 + slippage)
       
       # Determine exit conditions
       if stop_loss is not None and take_profit is not None:
           exit_second, exit_price, exit_reason = simulate_sl_tp_exit(
               market.prices, second_entered, adjusted_entry_price, direction,
               stop_loss, take_profit
           )
       else:
           # Existing hold-to-resolution logic
           exit_second = len(market.prices) - 1
           exit_price = market.prices[-1]
           if np.isnan(exit_price):
               exit_price = 1.0 if direction == 'Up' else 0.0
           exit_reason = 'resolution'
       
       # Calculate PnL using existing function
       pnl = calculate_pnl_exit(
           adjusted_entry_price, exit_price, direction, 
           trade_amount=100.0, base_rate=base_rate
       )
       
       return Trade(
           market_id=market.market_id,
           direction=direction,
           entry_price=adjusted_entry_price,
           exit_price=exit_price,
           entered_at=second_entered,
           exited_at=exit_second,
           pnl=pnl,
           trade_amount=100.0,
           exit_reason=exit_reason
       )
   ```

2. **`src/tests/test_sl_tp_engine.py`** — Complete test file with all test functions:
   - Fixture implementation: `synthetic_market()` creates MarketSnapshot with controlled prices
   - 12 test functions covering Up/Down × SL/TP/no-hit matrix + edge cases + PnL correctness
   - Each test:
     - Creates synthetic market with specific price movement
     - Calls make_trade() with appropriate SL/TP values
     - Asserts on exit_reason, exit_second, exit_price, PnL
     - Includes descriptive assertion messages for debugging

**Verification output:**
- pytest run shows 12 passed tests with detailed names
- Backward compatibility check prints "✓ Backward compatibility verified"
- SL/TP integration check prints "✓ SL/TP integration verified" with actual exit_reason value

**Test coverage achieved:**
- All exit paths exercised (sl, tp, resolution)
- Both directions tested (Up, Down)
- Edge cases covered (NaN, boundaries, simultaneous thresholds)
- PnL calculation verified via existing functions
- Backward compatibility proven (calls without SL/TP work)

## Observability Impact

**New signals introduced:**
- make_trade() now has explicit SL/TP parameters visible in function signature and call sites
- Trade objects created with SL/TP have exit_reason field populated with 'sl'/'tp' instead of always 'resolution'
- Test output shows exit_reason for each scenario, making correct behavior immediately visible

**Diagnostic value:**
- Test names describe scenario (test_up_bet_sl_hit) → failing test immediately identifies broken path
- Assertion messages include expected vs actual values → test failure output is self-documenting
- PnL tests verify calculate_pnl_exit() integration → catches fee calculation bugs
- Backward compatibility test proves old code paths still work → prevents regression

**State inspection:**
- Trade objects have all exit information: exit_reason, exit_second, exit_price, pnl
- Can filter trades by exit_reason in downstream analysis (S04 will do this)
- Test fixtures create reproducible scenarios → debugging is deterministic
- Synthetic markets have controlled price movements → easy to hand-verify expected outcomes

**Failure modes made visible:**
- Wrong exit_reason → test immediately fails with clear assertion message
- Incorrect exit_second → test fails with "expected second X, got Y"
- Wrong PnL calculation → PnL test fails with numerical difference
- Broken backward compatibility → compatibility test crashes with AttributeError or wrong exit_reason
- NaN handling bug → NaN test fails or crashes with exception
- Direction handling bug → Down bet tests fail while Up bet tests pass (or vice versa)

**Test maintainability:**
- Synthetic market fixture is reusable across all tests
- Each test is independent (no shared state)
- Test data is explicit (price arrays visible in test code)
- Adding new test scenarios is straightforward (copy pattern, adjust prices/thresholds)

**Performance verification:**
- Tests run in <1 second total (synthetic data, no DB access)
- O(1) memory (no large allocations)
- Proves engine is fast enough for grid search (300-second price scans are cheap)
