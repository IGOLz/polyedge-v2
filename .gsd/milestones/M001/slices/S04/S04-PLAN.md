# S04: Port S2 + parity verification

**Goal:** S2 (volatility) strategy ported into `shared/strategies/S2/`, and a parity test script proves both adapters produce identical signals on identical data — the seconds-vs-ticks bug is provably eliminated.
**Demo:** `cd src && PYTHONPATH=. python3 scripts/parity_test.py` exits 0, proving S1 and S2 produce identical signals regardless of adapter context. `discover_strategies()` returns both `S1` and `S2`.

## Must-Haves

- `shared/strategies/S2/` with `__init__.py`, `config.py`, `strategy.py` implementing the M4 volatility detection logic
- S2 config parameters match `M4_CONFIG` exactly (D005)
- S2 `evaluate()` is synchronous, pure, operates on `MarketSnapshot.prices` numpy array (D001, D004)
- Backtest adapter's Signal→Trade bridge handles S2's `entry_second` key (not just `reversion_second`)
- `scripts/parity_test.py` asserts identical signals from identical `MarketSnapshot` data for both S1 and S2
- Registry auto-discovers both S1 and S2
- S01 and S02 verification scripts still pass (no regressions)

## Proof Level

- This slice proves: contract verification (strategies are pure functions — identical input → identical output)
- Real runtime required: no
- Human/UAT required: no

## Verification

- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — exit 0, all parity checks pass
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; r = discover_strategies(); assert 'S2' in r and 'S1' in r, r; print('OK:', sorted(r))"` — registry discovers both
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — S01 regression check passes
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — S02 regression check passes (after adapter fix)
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies.S2.strategy import S2Strategy; from shared.strategies.S2.config import get_default_config; import numpy as np; from shared.strategies.base import MarketSnapshot; s = S2Strategy(get_default_config()); flat = MarketSnapshot(market_id='test', market_type='test', prices=np.full(60, 0.50), total_seconds=300, elapsed_seconds=60); assert s.evaluate(flat) is None; print('S2 correctly returns None on flat data')"` — failure-path diagnostic: S2 returns None on non-volatile data

## Observability / Diagnostics

- **Runtime signals:** S2 `evaluate()` returns `None` (no signal) or a `Signal` with `signal_data` containing `eval_second`, `spread`, `volatility`, `entry_second`, and `price_at_eval` — these keys are the primary diagnostic surface for understanding why S2 fired or didn't.
- **Inspection surfaces:** `discover_strategies()` returns a dict of registered strategy IDs → classes; checking `'S2' in discover_strategies()` confirms registration. The backtest adapter's `run_strategy()` prints `[S2] Evaluating N markets → M trades` to stdout.
- **Failure visibility:** S2 `evaluate()` silently returns `None` on any guard failure (insufficient data, low deviation, tight spread, low volatility). To diagnose why S2 didn't fire on specific data, construct a `MarketSnapshot` and inspect which guard rejects — all checks are ordered and short-circuiting.
- **Redaction constraints:** None — no secrets or PII in strategy signals or configs.

## Integration Closure

- Upstream surfaces consumed: `shared/strategies/base.py` (BaseStrategy, StrategyConfig, MarketSnapshot, Signal), `shared/strategies/registry.py` (discover_strategies), `analysis/backtest_strategies.py` (Signal→Trade bridge at line 81), `trading/strategy_adapter.py` (ticks_to_snapshot)
- New wiring introduced in this slice: none — S2 is auto-discovered by the existing registry, adapter fix is a one-line change
- What remains before the milestone is truly usable end-to-end: S05 (strategy template + parameter optimization)

## Tasks

- [x] **T01: Port S2 volatility strategy and fix backtest adapter entry_second** `est:25m`
  - Why: S2 must exist before parity testing can cover multiple strategies. The backtest adapter's `reversion_second` hardcoding must become generic so S2 trades enter at the correct second.
  - Files: `src/shared/strategies/S2/__init__.py`, `src/shared/strategies/S2/config.py`, `src/shared/strategies/S2/strategy.py`, `src/analysis/backtest_strategies.py`
  - Do: Create S2 strategy files following S1's pattern. Port M4 volatility logic from `trading/strategies.py::evaluate_m4_signal()` — strip all guards (balance, timing, DB, async), operate on `MarketSnapshot.prices` numpy array. Config from `trading/constants.py::M4_CONFIG`. Fix backtest adapter line 81: `signal_data.get('reversion_second', 0)` → `signal_data.get('entry_second', signal_data.get('reversion_second', 0))`. S2's signal_data must include `entry_second` = `eval_second`.
  - Verify: `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; r = discover_strategies(); assert 'S2' in r; print('OK')"` and `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` still passes
  - Done when: S2 strategy evaluates correctly on synthetic volatility data, registry discovers both S1 and S2, backtest adapter uses generic entry_second fallback, verify_s01.py and verify_s02.py still pass

- [x] **T02: Build parity test script proving identical signals across adapters** `est:20m`
  - Why: This is the core deliverable proving R007 — same data → same signals regardless of adapter. Eliminates the seconds-vs-ticks bug by construction.
  - Files: `src/scripts/parity_test.py`
  - Do: Create parity test script that: (a) constructs synthetic price data triggering S1 (spike+reversion) and S2 (volatility), (b) builds identical MarketSnapshot objects, (c) runs both strategies via direct `evaluate()` calls, (d) asserts signal equality (direction, entry_price, strategy_id), (e) verifies no-signal parity on flat data, (f) verifies registry discovers both strategies. The key insight: strategies are pure functions on `MarketSnapshot.prices` — if the prices array is identical, signals are guaranteed identical regardless of adapter context.
  - Verify: `cd src && PYTHONPATH=. python3 scripts/parity_test.py` exits 0
  - Done when: Parity test passes for S1, S2, and no-signal cases; script serves as the definitive proof that both adapters produce identical signals on identical data

## Files Likely Touched

- `src/shared/strategies/S2/__init__.py`
- `src/shared/strategies/S2/config.py`
- `src/shared/strategies/S2/strategy.py`
- `src/analysis/backtest_strategies.py`
- `src/scripts/parity_test.py`
