# T02: Implement simulate_sl_tp_exit() core function

**Description:** Implement the core price-scanning engine that detects when stop loss or take profit thresholds are hit. The function scans a numpy array of prices second-by-second from entry onward, handles direction-specific threshold logic (Up vs Down bets), skips NaN prices, prioritizes stop loss over take profit when both trigger simultaneously, and returns the exit second, exit price, and exit reason.

**Context from slice goal:** This is the heart of the SL/TP engine. The function must implement the exact threshold logic documented in decision D012: absolute price thresholds with engine-side direction handling. For Up bets, SL hits when price drops below threshold, TP hits when price rises above threshold. For Down bets, the engine must invert the logic because Down tokens have price `1.0 - up_price`. The legacy `strategy_momentum.py` demonstrates the pattern (lines 127-131 per research doc).

**Estimated duration:** 45m

## Steps

1. **Add function signature and docstring** — In `src/analysis/backtest/engine.py`, add the new function after existing helper functions but before `make_trade()`:
   ```python
   def simulate_sl_tp_exit(
       prices: np.ndarray,
       entry_second: int,
       entry_price: float,
       direction: str,
       stop_loss: float,
       take_profit: float
   ) -> tuple[int, float, str]:
       """Simulate early exit when stop loss or take profit threshold is hit.
       
       Args:
           prices: Array of prices indexed by elapsed seconds
           entry_second: Second when trade was entered
           entry_price: Price at entry (for reference, not used in logic)
           direction: 'Up' or 'Down'
           stop_loss: Absolute price threshold for SL (assuming Up bet)
           take_profit: Absolute price threshold for TP (assuming Up bet)
       
       Returns:
           (exit_second, exit_price, exit_reason) tuple where exit_reason is 'sl', 'tp', or 'resolution'
       
       Direction handling (per D012):
       - Up bets: SL when price <= stop_loss, TP when price >= take_profit
       - Down bets: Invert thresholds (Down token price = 1.0 - up_price)
           SL when price >= 1.0 - stop_loss
           TP when price <= 1.0 - take_profit
       
       NaN handling: Skips invalid prices, checks next valid second.
       If both SL and TP hit in same second, prioritizes SL (risk management).
       """
   ```

2. **Implement Up bet logic first** — Inside the function, start with the simpler Up bet case:
   - Loop from `entry_second + 1` to `len(prices) - 1`
   - For each second, get `current_price = prices[second]`
   - Skip if `np.isnan(current_price)` (continue to next second)
   - Check SL: if `current_price <= stop_loss`, return `(second, current_price, 'sl')`
   - Check TP: if `current_price >= take_profit`, return `(second, current_price, 'tp')`
   - If loop completes, return `(len(prices) - 1, prices[-1], 'resolution')`

3. **Add Down bet direction handling** — Wrap the Up bet logic in a direction check:
   - If `direction == 'Down'`, transform thresholds before the loop:
     ```python
     # Down token has price 1.0 - up_price, so invert thresholds
     sl_threshold = 1.0 - stop_loss
     tp_threshold = 1.0 - take_profit
     # For Down bets: SL when price >= sl_threshold, TP when price <= tp_threshold
     ```
   - Adjust the threshold comparisons inside the loop for Down bets:
     - SL: `current_price >= sl_threshold`
     - TP: `current_price <= tp_threshold`
   - Keep Up bet logic unchanged

4. **Handle edge case: both thresholds hit in same second** — Before returning 'tp', verify SL didn't also hit:
   - For Up bets: if `current_price >= take_profit` AND `current_price <= stop_loss`, return 'sl' (impossible in practice but code should be defensive)
   - For Down bets: if `current_price <= tp_threshold` AND `current_price >= sl_threshold`, return 'sl'
   - In practice, SL check comes first in code order, so this is automatically prioritized

5. **Handle resolution edge case: final price is NaN** — If loop completes but `prices[-1]` is NaN, the market still has a resolution outcome (1.0 for win, 0.0 for loss). For this task, return the last valid price found during scan, or if all prices after entry are NaN, return `entry_price` as fallback. Document this edge case in comments.

6. **Verify with manual smoke test** — Run the smoke test from research doc:
   ```python
   import numpy as np
   from analysis.backtest.engine import simulate_sl_tp_exit
   
   # Up bet, price drops to hit SL
   prices = np.array([0.55, 0.53, 0.48, 0.45, 0.40, 0.38])
   exit_sec, exit_price, reason = simulate_sl_tp_exit(
       prices, entry_second=0, entry_price=0.55, 
       direction='Up', stop_loss=0.45, take_profit=0.70
   )
   assert exit_sec == 3 and exit_price == 0.45 and reason == 'sl', f"Expected (3, 0.45, 'sl'), got ({exit_sec}, {exit_price}, '{reason}')"
   
   # Up bet, price rises to hit TP
   prices = np.array([0.55, 0.58, 0.62, 0.68, 0.72, 0.75])
   exit_sec, exit_price, reason = simulate_sl_tp_exit(
       prices, entry_second=0, entry_price=0.55,
       direction='Up', stop_loss=0.45, take_profit=0.70
   )
   assert exit_sec == 4 and exit_price == 0.72 and reason == 'tp', f"Expected (4, 0.72, 'tp'), got ({exit_sec}, {exit_price}, '{reason}')"
   
   print('✓ Smoke tests pass')
   ```

## Must-Haves

- `simulate_sl_tp_exit()` function exists in `src/analysis/backtest/engine.py`
- Function signature: `(prices, entry_second, entry_price, direction, stop_loss, take_profit) -> tuple[int, float, str]`
- Up bet logic: SL when `price <= stop_loss`, TP when `price >= take_profit`
- Down bet logic: SL when `price >= 1.0 - stop_loss`, TP when `price <= 1.0 - take_profit` (thresholds inverted)
- NaN handling: skip invalid seconds, check next valid price
- SL priority: if both hit in same second, return 'sl' (risk management over profit taking)
- Resolution fallback: if no threshold hit before end of prices array, return `('resolution', last_valid_price, len(prices)-1)`
- Comprehensive docstring explaining direction handling per D012

## Verification

Run the manual smoke test defined in step 6 above:

```bash
cd src && python3 << 'EOF'
import numpy as np
from analysis.backtest.engine import simulate_sl_tp_exit

# Up bet, price drops to hit SL
prices = np.array([0.55, 0.53, 0.48, 0.45, 0.40, 0.38])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.55, 
    direction='Up', stop_loss=0.45, take_profit=0.70
)
assert exit_sec == 3 and exit_price == 0.45 and reason == 'sl', f"Expected (3, 0.45, 'sl'), got ({exit_sec}, {exit_price}, '{reason}')"

# Up bet, price rises to hit TP
prices = np.array([0.55, 0.58, 0.62, 0.68, 0.72, 0.75])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.55,
    direction='Up', stop_loss=0.45, take_profit=0.70
)
assert exit_sec == 4 and exit_price == 0.72 and reason == 'tp', f"Expected (4, 0.72, 'tp'), got ({exit_sec}, {exit_price}, '{reason}')"

# Down bet (basic sanity check - comprehensive tests in T03)
prices = np.array([0.45, 0.48, 0.52, 0.55, 0.60, 0.65])
exit_sec, exit_price, reason = simulate_sl_tp_exit(
    prices, entry_second=0, entry_price=0.45,
    direction='Down', stop_loss=0.45, take_profit=0.70
)
# Down bet with SL=0.45 → inverted threshold=0.55
# Price rises to 0.55 at second 3 → should hit SL
assert reason == 'sl', f"Down bet: expected 'sl', got '{reason}'"

print('✓ All smoke tests pass')
EOF
```

Command must succeed with exit code 0 and print "✓ All smoke tests pass".

## Inputs

- Existing `src/analysis/backtest/engine.py` file with numpy imported
- Trade dataclass extended with exit_reason field (from T01)
- Research doc guidance on direction handling and legacy code pattern

## Expected Output

**Files modified:**
- `src/analysis/backtest/engine.py` — New function added (~50-70 lines including docstring):
  ```python
  def simulate_sl_tp_exit(
      prices: np.ndarray,
      entry_second: int,
      entry_price: float,
      direction: str,
      stop_loss: float,
      take_profit: float
  ) -> tuple[int, float, str]:
      """Simulate early exit when stop loss or take profit threshold is hit.
      
      [Full docstring from step 1]
      """
      
      # Direction-specific threshold setup
      if direction == 'Down':
          # Down token price = 1.0 - up_price, so invert thresholds
          sl_threshold = 1.0 - stop_loss
          tp_threshold = 1.0 - take_profit
      else:  # 'Up'
          sl_threshold = stop_loss
          tp_threshold = take_profit
      
      # Scan prices from entry onward
      last_valid_price = entry_price
      for second in range(entry_second + 1, len(prices)):
          current_price = prices[second]
          
          # Skip NaN prices
          if np.isnan(current_price):
              continue
          
          last_valid_price = current_price
          
          # Check thresholds based on direction
          if direction == 'Down':
              # Down bet: SL when price rises above sl_threshold
              if current_price >= sl_threshold:
                  return (second, current_price, 'sl')
              # TP when price drops below tp_threshold
              if current_price <= tp_threshold:
                  return (second, current_price, 'tp')
          else:  # 'Up'
              # Up bet: SL when price drops below sl_threshold
              if current_price <= sl_threshold:
                  return (second, current_price, 'sl')
              # TP when price rises above tp_threshold
              if current_price >= tp_threshold:
                  return (second, current_price, 'tp')
      
      # No threshold hit - hold to resolution
      return (len(prices) - 1, last_valid_price, 'resolution')
  ```

**Verification output:**
- Smoke test command prints "✓ All smoke tests pass"
- Up bet SL scenario: exits at second 3 with price 0.45 and reason 'sl'
- Up bet TP scenario: exits at second 4 with price 0.72 and reason 'tp'
- Down bet SL scenario: exits with reason 'sl' when price rises above inverted threshold

## Observability Impact

**New signals introduced:**
- Function returns exit_reason string with three possible values: 'sl', 'tp', 'resolution'
- exit_second indicates exactly when threshold was hit (or market close if resolution)
- exit_price is the actual market price at exit time (not the threshold value)

**Diagnostic value:**
- NaN skipping visible in logic flow — if function returns late exit_second, indicates NaN gaps in price data
- Direction handling is explicit — traceback from wrong exit will point to direction=='Down' vs 'Up' branch
- Threshold comparisons are literal — no complex math, easy to verify in debugger

**State inspection:**
- Function is pure and deterministic — same inputs always produce same output
- No internal state, no side effects, no logging
- Can be tested in isolation with synthetic numpy arrays (T03 will do this comprehensively)
- For debugging: print current_price, sl_threshold, tp_threshold inside loop (commented out in production)

**Failure modes made visible:**
- Wrong direction handling → systematic pattern of incorrect exits for all Up or all Down bets
- Off-by-one error in loop range → exit_second consistently wrong by 1
- NaN handling bug → function crashes with NaN in comparison (would raise exception)
- Missing resolution fallback → function crashes if no threshold hit (would fall through to no return)

**Performance characteristics:**
- O(n) scan where n = seconds in market (typically 300)
- Each second: 2-4 float comparisons + 1 NaN check
- No allocations, no copies of price array
- Fast enough for grid search with 1000s of markets × 1000s of parameter combinations
