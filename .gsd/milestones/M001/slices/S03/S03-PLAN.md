# S03: Trading adapter — live signals through shared strategies

**Goal:** Trading bot's main loop evaluates strategies from the shared registry, converting live ticks to MarketSnapshot, producing Signal objects the executor accepts — without modifying executor, redeemer, or balance.
**Demo:** `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` passes all checks — synthetic ticks convert to MarketSnapshot, shared strategy evaluate() fires, adapter populates all executor-required fields, and no existing trading modules are modified.

## Must-Haves

- `trading/strategy_adapter.py` exists with `ticks_to_snapshot()` and `evaluate_strategies()` matching the async signature
- `ticks_to_snapshot()` converts `list[Tick]` → `MarketSnapshot` with prices indexed by elapsed second (NaN for missing), correct `elapsed_seconds` reflecting live context
- Adapter populates `locked_shares`, `locked_cost`, `locked_balance`, `locked_bet_size` via balance fetch + bet sizing
- Adapter populates `signal_data` keys the executor reads: `bet_cost`, `shares`, `price_min`, `price_max`, `stop_loss_price`, `profitability_thesis`, `balance_at_signal`, `seconds_elapsed`, `seconds_remaining`
- `trading/main.py` imports `evaluate_strategies` from `trading.strategy_adapter` instead of `trading.strategies`
- `executor.py`, `redeemer.py`, `balance.py` have zero modifications (R009)
- Guard logic: `already_traded_this_market()` check, empty ticks handled, balance fetch failure handled

## Proof Level

- This slice proves: integration
- Real runtime required: no (contract verification with synthetic data; real runtime deferred to S04 parity test)
- Human/UAT required: no

## Verification

- `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — contract verification script covering:
  1. Import chain resolves (shared.strategies + trading.strategy_adapter)
  2. `ticks_to_snapshot()` produces correct numpy array (NaN for missing seconds, correct values for present seconds)
  3. `elapsed_seconds` reflects live context (< total_seconds)
  4. Shared strategy `evaluate()` returns Signal on synthetic spike data
  5. Adapter populates all `locked_*` fields
  6. Adapter populates executor-required `signal_data` keys
  7. `evaluate_strategies()` returns list matching old async signature shape
  8. No modifications to `executor.py`, `redeemer.py`, `balance.py` (file hash check against main repo)
  9. Module isolation: adapter imports only from `shared.strategies`, `trading.balance`, `trading.db`, `trading.constants`, `trading.strategies` (no `analysis.*`)
  10. Empty ticks returns empty signal list (no crash)
  11. Failure path: adapter logs warning and returns `[]` when balance fetch fails (no crash, structured error output via logger)
  12. Diagnostic surface: `ticks_to_snapshot()` raises TypeError/ValueError immediately on bad input (inspectable via traceback, not silent failure)

## Observability / Diagnostics

- Runtime signals: adapter logs strategy evaluation count per market (matching existing M3/M4 log pattern)
- Inspection surfaces: `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` exit code 0/1; adapter module is importable standalone
- Failure visibility: `ticks_to_snapshot()` is a pure function — failures are immediate ValueError/TypeError; `evaluate_strategies()` mirrors existing error handling pattern (catch + log + continue)
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `shared/strategies/base.py` (MarketSnapshot, Signal, BaseStrategy), `shared/strategies/registry.py` (discover_strategies, get_strategy), `trading/db.py` (MarketInfo, Tick, already_traded_this_market), `trading/balance.py` (get_usdc_balance), `trading/constants.py` (BET_SIZING), `trading/strategies.py` (calculate_dynamic_bet_size, calculate_shares — pure functions)
- New wiring introduced in this slice: `trading/main.py` import rewired from `trading.strategies.evaluate_strategies` → `trading.strategy_adapter.evaluate_strategies`
- What remains before the milestone is truly usable end-to-end: S04 (parity verification — proves both adapters produce identical signals), S05 (template + optimization)

## Tasks

- [x] **T01: Build trading strategy adapter module** `est:30m`
  - Why: Core deliverable — converts live ticks to MarketSnapshot, runs shared strategies, populates executor-required signal fields. Without this, the trading bot cannot use shared strategies.
  - Files: `src/trading/strategy_adapter.py`
  - Do: Create `trading/strategy_adapter.py` with `ticks_to_snapshot(market, ticks)` → MarketSnapshot (numpy array indexed by elapsed second, NaN for missing, `elapsed_seconds` = real elapsed time), then `evaluate_strategies(market, ticks)` as async function that: checks guards (already_traded, empty ticks), calls `ticks_to_snapshot()`, iterates shared strategies via registry, calls `strategy.evaluate(snapshot)`, populates `locked_*` fields via `get_usdc_balance()` + `calculate_dynamic_bet_size()`, populates all executor-required `signal_data` keys, returns `list[Signal]`. Import bet sizing functions from `trading.strategies` (they're pure functions, file stays in place per D007). Follow D001 (sync evaluate, async wrapper), D006 (all 10 executor fields), R009 (no executor changes).
  - Verify: `cd src && PYTHONPATH=. python3 -c "from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot; print('OK')"`
  - Done when: Module imports cleanly and exports both `ticks_to_snapshot` and `evaluate_strategies` with correct signatures

- [x] **T02: Rewire main.py import + build verification script** `est:25m`
  - Why: Completes integration by wiring the adapter into the bot's main loop and proves the entire chain works via contract verification. Without the import change, the bot still uses old hardcoded strategies.
  - Files: `src/trading/main.py`, `src/scripts/verify_s03.py`
  - Do: (1) In `trading/main.py`, change `from trading.strategies import evaluate_strategies` to `from trading.strategy_adapter import evaluate_strategies` — this is the only line that changes in main.py. (2) Build `scripts/verify_s03.py` following the verify_s01.py/verify_s02.py pattern with 10+ checks: import chain, tick-to-snapshot conversion (NaN handling, elapsed_seconds), strategy evaluation on synthetic spike data, `locked_*` field population, `signal_data` key completeness, empty-ticks handling, `evaluate_strategies` return type, file hash integrity for executor.py/redeemer.py/balance.py (compared against originals in main repo at `/Users/igol/Documents/repo/polyedge/`), and module isolation (no analysis.* imports in adapter). Use the S1 synthetic data calibration from KNOWLEDGE.md (spike peak early, sharp reversion, entry_price ≤ 0.35).
  - Verify: `cd src && PYTHONPATH=. python3 scripts/verify_s03.py` — all checks pass (exit code 0)
  - Done when: Verification script passes all checks, proving the adapter produces correct MarketSnapshot and executor-compatible Signal objects from synthetic tick data

## Files Likely Touched

- `src/trading/strategy_adapter.py` — NEW: adapter module
- `src/trading/main.py` — 1-line import change
- `src/scripts/verify_s03.py` — NEW: contract verification script
