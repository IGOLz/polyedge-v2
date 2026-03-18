---
estimated_steps: 6
estimated_files: 1
---

# T01: Build trading strategy adapter module

**Slice:** S03 — Trading adapter — live signals through shared strategies
**Milestone:** M001

## Description

Create `src/trading/strategy_adapter.py` — the adapter that bridges the shared strategy framework into the trading bot's evaluation loop. This module converts live `list[Tick]` to `MarketSnapshot`, runs shared strategies via the registry, and populates all executor-required fields on the returned Signal objects. It exports `evaluate_strategies(market, ticks) -> list[Signal]` with the same async signature as the function it replaces in `trading/strategies.py`.

The adapter follows the same composition pattern established in S02's `analysis/backtest_strategies.py` (D008): a new module that composes `shared.strategies` + existing infrastructure without modifying either side.

Key decisions:
- D001: Strategy `evaluate()` is synchronous — the adapter wraps it in an async function that handles async balance fetch and DB queries separately
- D006: Shared Signal includes all 10 executor-required fields with zero/empty defaults — adapter fills `locked_*` and execution `signal_data` keys
- D007: `trading/strategies.py` stays in place — adapter imports pure functions (`calculate_dynamic_bet_size`, `calculate_shares`) from it
- R009: executor.py, redeemer.py, balance.py must not be modified

## Steps

1. Create `src/trading/strategy_adapter.py` with imports:
   - From `shared.strategies`: `MarketSnapshot`, `Signal`, `discover_strategies`
   - From `trading.db`: `MarketInfo`, `Tick`, `already_traded_this_market`
   - From `trading.balance`: `get_usdc_balance`
   - From `trading.constants`: `BET_SIZING`
   - From `trading.strategies`: `calculate_dynamic_bet_size`, `calculate_shares`
   - From `trading.utils`: `log`, `debug_log`
   - Standard: `numpy`, `datetime`

2. Implement `ticks_to_snapshot(market: MarketInfo, ticks: list[Tick]) -> MarketSnapshot`:
   ```python
   def ticks_to_snapshot(market: MarketInfo, ticks: list[Tick]) -> MarketSnapshot:
       total_seconds = int((market.ended_at - market.started_at).total_seconds())
       elapsed_seconds = (datetime.now(timezone.utc) - market.started_at).total_seconds()
       
       prices = np.full(total_seconds, np.nan)
       for tick in ticks:
           second = int((tick.time - market.started_at).total_seconds())
           if 0 <= second < total_seconds:
               prices[second] = tick.up_price  # last-write-wins for same second
       
       return MarketSnapshot(
           market_id=market.market_id,
           market_type=market.market_type,
           prices=prices,
           total_seconds=total_seconds,
           elapsed_seconds=elapsed_seconds,
           metadata={'started_at': market.started_at},
       )
   ```
   Key: `elapsed_seconds` is real elapsed time (not total_seconds — this is the live context difference from S02). NaN for missing seconds. `int()` truncation handles fractional tick timestamps.

3. Implement `_populate_execution_fields(signal: Signal, market: MarketInfo, snapshot: MarketSnapshot, balance: float) -> Signal`:
   - Calculate bet sizing: `bet_size = calculate_dynamic_bet_size(balance)`, `shares = calculate_shares(signal.entry_price, bet_size)`, `actual_cost = shares * signal.entry_price`
   - Check `actual_cost > balance * BET_SIZING['max_single_trade_pct']` — if so, return None (trade too large)
   - Populate locked fields: `signal.locked_shares = shares`, `signal.locked_cost = round(actual_cost, 4)`, `signal.locked_balance = round(balance, 2)`, `signal.locked_bet_size = round(bet_size, 2)`
   - Merge execution keys into `signal.signal_data`:
     - `bet_cost`: `round(actual_cost, 4)`
     - `shares`: shares
     - `actual_cost`: `round(actual_cost, 2)`
     - `price_min`: `0.01`
     - `price_max`: `0.99`
     - `stop_loss_price`: `None` (unless strategy config specifies one)
     - `profitability_thesis`: descriptive string using signal_data context
     - `balance_at_signal`: `round(balance, 2)`
     - `current_balance`: `round(balance, 2)`
     - `bet_size`: `round(bet_size, 2)`
     - `seconds_elapsed`: `round(snapshot.elapsed_seconds, 1)`
     - `seconds_remaining`: `round(snapshot.total_seconds - snapshot.elapsed_seconds, 1)`
   - Return the populated signal

4. Implement `async def evaluate_strategies(market: MarketInfo, ticks: list[Tick]) -> list[Signal]`:
   - **Guard: empty ticks** — if `len(ticks) < 2`, return `[]`
   - Build snapshot via `ticks_to_snapshot(market, ticks)`
   - Fetch balance via `await get_usdc_balance()` — if `<= 0`, log warning and return `[]`
   - Iterate through strategies via `discover_strategies()`:
     - For each strategy: call `await already_traded_this_market(market.market_id, strategy.config.strategy_name)` — if True, skip
     - Call `strategy.evaluate(snapshot)` (synchronous, per D001) — if returns None, skip
     - Call `_populate_execution_fields(signal, market, snapshot, balance)` — if returns None (bet too large), skip
     - Append to signals list
   - Log signal count per market (matching existing pattern)
   - Return signals list

5. Add module-level docstring explaining the adapter's role, usage, and relationship to `trading/strategies.py`.

6. Verify the module imports correctly:
   ```
   cd src && PYTHONPATH=. python3 -c "from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot; print('OK')"
   ```

## Must-Haves

- [ ] `ticks_to_snapshot()` produces MarketSnapshot with numpy array indexed by elapsed second, NaN for missing, `elapsed_seconds` < `total_seconds` in live context
- [ ] `evaluate_strategies()` has async signature `(market: MarketInfo, ticks: list[Tick]) -> list[Signal]`
- [ ] All 4 `locked_*` fields populated (locked_shares, locked_cost, locked_balance, locked_bet_size)
- [ ] All executor-required `signal_data` keys populated (bet_cost, shares, price_min, price_max, stop_loss_price, profitability_thesis, balance_at_signal, seconds_elapsed, seconds_remaining)
- [ ] Guard: empty ticks returns `[]`, balance failure returns `[]`, already-traded check skips strategy
- [ ] No modifications to any existing file — this is a new file only

## Verification

- `cd src && PYTHONPATH=. python3 -c "from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot; print('OK')"` succeeds
- `cd src && PYTHONPATH=. python3 -c "import inspect; from trading.strategy_adapter import evaluate_strategies; print(inspect.iscoroutinefunction(evaluate_strategies))"` prints `True`
- File contains no imports from `analysis.*` or `core.*`

## Inputs

- `src/shared/strategies/base.py` — MarketSnapshot, Signal, BaseStrategy definitions (from S01)
- `src/shared/strategies/registry.py` — discover_strategies(), get_strategy() (from S01)
- `src/trading/db.py` — MarketInfo, Tick, already_traded_this_market types/functions (existing, unmodified)
- `src/trading/balance.py` — get_usdc_balance() async function (existing, unmodified)
- `src/trading/constants.py` — BET_SIZING dict (existing, unmodified)
- `src/trading/strategies.py` — calculate_dynamic_bet_size(), calculate_shares() pure functions (existing, unmodified)

## Observability Impact

- **New signals:** Adapter logs strategy evaluation count per market via `log.info("[ADAPTER] %d signals for %s", ...)` matching existing M3/M4 log pattern. Each strategy skip (already-traded, no signal, bet-too-large) is logged via `debug_log.info()`.
- **Inspection:** `ticks_to_snapshot()` is a pure function — call it standalone to verify tick-to-snapshot conversion. `evaluate_strategies()` mirrors existing error handling (catch + log + continue per strategy).
- **Failure visibility:** Balance fetch failure → `log.warning()` + empty return. Bad tick data → immediate TypeError/ValueError. Strategy evaluation exceptions → caught per-strategy, logged via `debug_log`, loop continues.

## Expected Output

- `src/trading/strategy_adapter.py` — new adapter module with `ticks_to_snapshot()` and `evaluate_strategies()` that bridges shared strategy framework into the trading evaluation loop
