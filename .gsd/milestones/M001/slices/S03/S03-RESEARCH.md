# S03 — Research

**Date:** 2026-03-18

## Summary

S03 wires the shared strategy framework into the trading bot's main evaluation loop. The current `trading/strategies.py` contains ~400 lines of hardcoded M3/M4 strategy logic plus bet sizing, signal creation, and a `Signal` dataclass. The entry point is `evaluate_strategies(market, ticks) -> list[Signal]`, called from `trading/main.py`'s main loop. The adapter must replace this call path with one that loads strategies from `shared.strategies`, converts live `list[Tick]` to `MarketSnapshot`, runs `strategy.evaluate()`, then populates the execution-specific fields (`locked_*`, `signal_data` keys for bet sizing) that the executor expects.

The work is straightforward — it follows the exact same adapter composition pattern established in S02. The key conversion is `list[Tick]` → `MarketSnapshot`: each Tick has a `time` (datetime) and `up_price` (float); the adapter computes elapsed seconds from `market.started_at`, builds a numpy array indexed by elapsed second with NaN for missing seconds, and wraps it in a MarketSnapshot. The executor uses pure duck-typing on Signal (no isinstance checks), so the shared `Signal` dataclass works without modification. Two files in `trading/` import from `trading.strategies`: `main.py` (imports `evaluate_strategies`) and `executor.py` (imports `Signal`). Both must be rewired to use shared equivalents.

## Recommendation

Build a single new adapter module (`trading/strategy_adapter.py`) that:
1. Converts `list[Tick]` → `MarketSnapshot` (the core tick-to-seconds normalization)
2. Wraps shared `strategy.evaluate()` with bet sizing and execution field population
3. Exports `evaluate_strategies(market, ticks) -> list[Signal]` with the same async signature

Then rewire the two import sites in `trading/main.py` and `trading/executor.py`. The executor's `from trading.strategies import Signal` changes to `from shared.strategies import Signal` — this is safe because the shared Signal has identical fields (confirmed by S01's D006 decision). The original `trading/strategies.py` stays in place untouched (it can be deprecated later per D007).

**Wait — R009 says executor must remain unchanged.** Re-reading R009: "Executor, redeemer, balance, bot_trades DB tables remain unchanged; only the strategy evaluation path is rewired." This means `executor.py` cannot be modified. The adapter must produce objects that satisfy the executor's attribute access pattern. Since executor does `from trading.strategies import Signal` and only uses attribute access (no isinstance), the simplest approach is: the adapter function returns `list[trading.strategies.Signal]` by constructing old-style Signal objects. Alternatively, the adapter can re-export `Signal` from shared.strategies and only change `main.py`'s import. But the executor's import of `Signal` from `trading.strategies` is never used at runtime to type-check — it's just for the type annotation in `execute_trade(signal: Signal)`. Python doesn't enforce type annotations at runtime.

**Cleanest approach:** Change only `trading/main.py` to import `evaluate_strategies` from the new adapter module instead of `trading.strategies`. The executor keeps importing `Signal` from `trading.strategies` — this is fine because it never type-checks, and the shared Signal objects have all the same attributes. Zero changes to executor.py.

## Implementation Landscape

### Key Files

- `src/trading/strategy_adapter.py` — **NEW**: the adapter module. Converts `list[Tick]` → `MarketSnapshot`, runs shared strategies via registry, populates `locked_*` execution fields and `signal_data` keys (`bet_cost`, `shares`, `price_min`, `price_max`, `stop_loss_price`, `profitability_thesis`, `balance_at_signal`) that the executor reads. Exports `evaluate_strategies(market, ticks) -> list[Signal]` matching the async signature.
- `src/trading/main.py` — **MODIFY** (1-line change): change `from trading.strategies import evaluate_strategies` to `from trading.strategy_adapter import evaluate_strategies`. This is the only modification to any existing file in `trading/`.
- `src/trading/executor.py` — **UNCHANGED**: keeps `from trading.strategies import Signal`. The shared Signal duck-types identically. R009 constraint satisfied.
- `src/trading/strategies.py` — **UNCHANGED**: stays in place. Old M3/M4 code preserved. Can be deprecated later.
- `src/trading/db.py` — **READ ONLY**: provides `MarketInfo`, `Tick`, `get_market_ticks()`, `already_traded_this_market()`. The adapter calls these but doesn't modify them.
- `src/trading/balance.py` — **READ ONLY**: provides `get_usdc_balance()`. The adapter calls this for bet sizing.
- `src/trading/constants.py` — **READ ONLY**: provides `BET_SIZING` for dynamic bet sizing. Strategies may have their own bet sizing overrides in config, but the adapter uses the global BET_SIZING as default.
- `src/shared/strategies/base.py` — **READ ONLY**: Signal, MarketSnapshot, BaseStrategy — consumed by adapter.
- `src/shared/strategies/registry.py` — **READ ONLY**: `discover_strategies()`, `get_strategy()` — consumed by adapter.
- `src/scripts/verify_s03.py` — **NEW**: contract verification script following the verify_s01.py/verify_s02.py pattern.

### Key Conversion: `list[Tick]` → `MarketSnapshot`

```python
def ticks_to_snapshot(market: MarketInfo, ticks: list[Tick]) -> MarketSnapshot:
    """Convert live tick stream to seconds-indexed MarketSnapshot."""
    total_seconds = int((market.ended_at - market.started_at).total_seconds())
    elapsed_seconds = (datetime.now(timezone.utc) - market.started_at).total_seconds()
    
    # Build numpy array indexed by elapsed second, NaN for missing
    prices = np.full(total_seconds, np.nan)
    for tick in ticks:
        second = int((tick.time - market.started_at).total_seconds())
        if 0 <= second < total_seconds:
            prices[second] = tick.up_price
    
    return MarketSnapshot(
        market_id=market.market_id,
        market_type=market.market_type,
        prices=prices,
        total_seconds=total_seconds,
        elapsed_seconds=elapsed_seconds,
        metadata={'started_at': market.started_at},
    )
```

Key differences from S02's `market_to_snapshot()`:
- **elapsed_seconds** = real elapsed time (not total_seconds) — live context, partial data
- **Tick → second mapping** uses `(tick.time - market.started_at).total_seconds()` — ticks have datetime timestamps, not array indices
- Multiple ticks in the same second: last-write-wins (latest tick overwrites). This matches the behavior of the current trading strategies which use `ticks[-1]` for current price.

### Key Conversion: Shared Signal → Execution-Ready Signal

After `strategy.evaluate(snapshot)` returns a Signal, the adapter must populate:
- `locked_shares`, `locked_cost`, `locked_balance`, `locked_bet_size` — computed from balance + bet sizing
- `signal_data` keys the executor reads via `.get()`:
  - `bet_cost` (fallback for locked_cost)
  - `price_min` (default 0.01)
  - `price_max` (default 0.99)
  - `stop_loss_price` (None unless strategy specifies)
  - `shares`, `actual_cost`, `current_balance`, `balance_at_signal` — informational
  - `profitability_thesis` — logging string
  - `bet_size` — for logging
  - `seconds_elapsed`, `seconds_remaining` — timing context

### Bet Sizing Integration

The current strategies call `get_usdc_balance()` (async) and `calculate_dynamic_bet_size()` inline. The adapter must do the same. These functions live in `trading/strategies.py` and `trading/balance.py`. The adapter should:
- Import `get_usdc_balance` from `trading.balance`
- Reimplement the simple bet sizing logic (or import `calculate_dynamic_bet_size` and `calculate_shares` from `trading.strategies` — they're pure functions with no side effects)

Importing from `trading.strategies` is acceptable — those functions are stable and won't be removed (the file stays in place per D007).

### Guard Logic

The current strategies have guards (market type filter, asset filter, already-traded check, timing window). Some of these should stay in the adapter layer (they're execution concerns, not strategy logic):
- `already_traded_this_market()` — must stay in adapter (DB query, async)
- Market type/asset filters — already in strategy config or can be adapter-level
- Timing window guards — the shared strategy handles this via `elapsed_seconds` in the snapshot

### Build Order

1. **T01: Trading adapter module** — Build `trading/strategy_adapter.py` with `ticks_to_snapshot()`, execution field population, and `evaluate_strategies()`. This is the core work. Import from `shared.strategies` for strategy registry and types, from `trading.balance` for balance, from `trading.db` for types and DB queries.

2. **T02: Rewire main.py + verification** — Change the 1-line import in `trading/main.py`. Build `scripts/verify_s03.py` with contract checks covering: import chain, tick-to-snapshot conversion (including NaN for missing seconds, correct elapsed_seconds), signal field completeness (all 10 executor-required fields populated), signal_data key completeness, duck-type compatibility with executor's access pattern, and module isolation (no modifications to executor/redeemer/balance).

### Verification Approach

1. **Contract verification script** (`scripts/verify_s03.py`): Synthetic ticks → MarketSnapshot → strategy.evaluate() → populated Signal. Checks:
   - Import chain resolves (shared.strategies + trading adapter)
   - `ticks_to_snapshot()` produces correct numpy array (NaN for missing seconds, correct values for present seconds)
   - `elapsed_seconds` reflects live context (< total_seconds)
   - Shared strategy evaluate() returns Signal on synthetic spike data
   - Adapter populates all `locked_*` fields (non-zero when balance > 0)
   - Adapter populates executor-required `signal_data` keys (`price_min`, `price_max`, `stop_loss_price`)
   - `evaluate_strategies()` returns `list` matching old signature shape
   - No modifications to executor.py, redeemer.py, balance.py (AST/hash check)
   - Module isolation: adapter imports only from shared.strategies, trading.balance, trading.db, trading.constants (no analysis.*)

2. **Runtime verification** (deferred, requires DB): `python3 -m trading.main --dry-run` starts without errors and logs strategy evaluation attempts.

## Constraints

- **R009**: executor.py, redeemer.py, balance.py, and bot_trades DB tables must not be modified. Only the strategy evaluation path is rewired.
- **D001**: Strategy evaluate() is synchronous. The adapter wraps it in an async function that handles the async balance fetch and DB queries separately from the sync evaluate() call.
- **D006**: Shared Signal must include all 10 executor-required fields. Already satisfied by S01 — base.py Signal has all fields with defaults.
- **Only `python3` available** — not `python` (S01 deviation, carried forward).
- **PYTHONPATH must include `src/`** — required for `shared.strategies` imports to resolve (S01 fragility note).

## Common Pitfalls

- **Tick timing precision** — `tick.time` is a database datetime; `(tick.time - market.started_at).total_seconds()` may produce fractional seconds. Must `int()` to get the array index. Ticks arriving at sub-second intervals for the same second should overwrite (last wins).
- **Empty tick list** — If `ticks` is empty, the adapter should return an empty signal list (no strategies can evaluate). Don't let numpy array creation fail on zero ticks.
- **Balance fetch failure** — `get_usdc_balance()` can return -1 on failure (current code checks `<= 0`). Adapter must handle this identically to current strategies.
- **Signal created_at timing** — The shared Signal's `created_at` defaults to `datetime.now(UTC)` at construction time. The executor measures signal age from this. The adapter should let the default work (signal is created at evaluation time).
