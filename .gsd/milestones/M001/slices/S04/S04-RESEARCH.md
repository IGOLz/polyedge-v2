# S04: Port S2 + parity verification — Research

**Date:** 2026-03-18

## Summary

S04 has two deliverables: (1) port M4 volatility as S2 into `shared/strategies/S2/`, and (2) build a parity test script proving both adapters produce identical signals on identical data. Both are straightforward applications of established patterns.

The S2 port follows the exact same structure as S1 — `config.py` with an `S2Config` dataclass + `get_default_config()`, and `strategy.py` with an `S2Strategy(BaseStrategy)` implementing `evaluate()`. The core detection logic comes from `trading/strategies.py::evaluate_m4_signal()` (the live version) stripped of all guards (balance, timing, DB, async) and operating on a `MarketSnapshot.prices` numpy array instead of `list[Tick]`. Parameters come from `trading/constants.py::M4_CONFIG`.

The parity test is mechanically simple because a critical property holds: **neither S1 nor S2's `evaluate()` uses `elapsed_seconds`** — they operate entirely on the `prices` numpy array. This means if both adapters produce a `MarketSnapshot` with the same `prices` array, the signals are guaranteed identical. The parity test constructs synthetic data, builds matching `MarketSnapshot` objects, runs both strategies through direct `evaluate()` calls, and asserts signal equality. No need to invoke the full adapter pipelines — the strategies are pure functions.

One small issue: the backtest adapter's Signal→Trade bridge (`backtest_strategies.py` line 81) hardcodes `signal_data.get('reversion_second', 0)` for `second_entered`. S2 uses `eval_second` (30) as its entry point, not `reversion_second`. This needs a one-line fix to become strategy-agnostic — e.g. `signal_data.get('entry_second', signal_data.get('reversion_second', 0))` — with S2 putting `entry_second` in its signal_data.

## Recommendation

Build S2 first (it's a prerequisite for multi-strategy parity testing), then the parity test. Two tasks:

**T01: Port S2 volatility strategy** — Create `shared/strategies/S2/{__init__.py, config.py, strategy.py}`. The strategy evaluates at `eval_second` (30), checks spread and volatility conditions, bets contrarian. Also fix the backtest adapter's `second_entered` extraction to handle S2's `eval_second` key.

**T02: Parity test script** — Create `scripts/parity_test.py` (also serves as `verify_s04.py`). Constructs synthetic data triggering both S1 and S2, builds identical `MarketSnapshot` objects, asserts `strategy.evaluate()` produces identical signals regardless of which adapter context the snapshot was built for. Additionally verifies S2 registry discovery.

## Implementation Landscape

### Key Files

- `src/trading/strategies.py` — contains `evaluate_m4_signal()` (lines ~260-400), the source of S2's detection logic. Port the volatility calculation, spread check, and contrarian direction determination. Strip all guards (enabled check, market filter, timing, DB, balance, async).
- `src/trading/constants.py` — contains `M4_CONFIG` with all parameter values: `eval_second=30`, `eval_window=2`, `volatility_window_seconds=10`, `volatility_threshold=0.05`, `min_spread=0.05`, `max_spread=0.50`.
- `src/shared/strategies/S1/` — the pattern to follow. `config.py` has `S1Config(StrategyConfig)` + `get_default_config()`. `strategy.py` has `S1Strategy(BaseStrategy)` with `evaluate(snapshot) -> Signal|None`. `__init__.py` is empty.
- `src/shared/strategies/registry.py` — auto-discovers `S2/strategy.py` by scanning directories. No changes needed.
- `src/analysis/backtest_strategies.py` line 81 — `signal_data.get('reversion_second', 0)` needs to become strategy-agnostic to handle S2's `eval_second`.
- `src/analysis/backtest/module_4_volatility.py` — the analysis-side M4 implementation. Contains `_compute_volatility()` (numpy std dev over window) and `run_single_config()` with the spread/volatility/deviation checks. Useful cross-reference for the detection logic but the trading version in `strategies.py` is simpler and closer to what S2 should be.

### S2 Strategy Logic (extracted from M4)

The S2 `evaluate()` function needs to:
1. Check `len(prices) > eval_second` (guard: enough data)
2. Get `price = prices[eval_second]` — must not be NaN
3. Check base deviation: `abs(price - 0.50) >= base_deviation` (0.08)
4. Check spread: `min_spread <= abs(2*price - 1) <= max_spread`
5. Compute volatility: `np.nanstd(prices[eval_second - vol_window : eval_second + 1])` over valid values, need >= 2 valid
6. Check `volatility >= volatility_threshold`
7. Contrarian: `price > 0.50` → Down (entry = 1-price), else Up (entry = price)
8. Return `Signal` with `signal_data` including `eval_second`, `spread`, `volatility`, `entry_second` (= `eval_second`)

Note: The analysis `module_4_volatility.py` uses `np.std()` (population std dev). The trading `strategies.py` uses a manual population std dev calculation. Both are equivalent — use `np.nanstd()` in S2 for NaN-safety.

### Build Order

1. **T01: S2 strategy + adapter fix** — Create `shared/strategies/S2/` (3 files). Fix `backtest_strategies.py` line 81 to use generic `entry_second` key. Verify with `discover_strategies()` finding both S1 and S2, and `S2Strategy.evaluate()` firing on calibrated synthetic data.

2. **T02: Parity test script** — Create `scripts/parity_test.py`. Must cover: (a) S1 parity — same prices → same signal via both adapter conversion paths, (b) S2 parity — same test, (c) multi-strategy discovery — registry finds both S1 and S2, (d) no-signal parity — flat data → both return None. The seconds-vs-ticks bug is proven eliminated by showing strategies operate on seconds-indexed numpy arrays in both contexts.

### Verification Approach

- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — exit code 0 = all parity checks pass
- `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; r = discover_strategies(); assert 'S2' in r and 'S1' in r, r; print('OK:', sorted(r))"` — registry discovers both
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — S01 still passes (regression)
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — S02 still passes after adapter fix

## Constraints

- Strategy `evaluate()` must be synchronous (D001) — no async, no DB, no side effects.
- S2 config parameters must match `M4_CONFIG` exactly (D005 — port as-is, don't optimize).
- `shared/strategies/` must not import from `trading`, `analysis`, or `core` (import isolation).
- The backtest adapter fix must not break S1's existing `reversion_second` behavior.

## Common Pitfalls

- **Volatility calculation mismatch** — `trading/strategies.py` uses manual population std dev; `module_4_volatility.py` uses `np.std()` (population by default). Both are equivalent, but S2 should use `np.nanstd()` for NaN-safety since `MarketSnapshot.prices` can contain NaN gaps. This is a subtle difference — `np.std()` on an array with NaN returns NaN, whereas `np.nanstd()` ignores NaN values.
- **Synthetic data for S2 must trigger the volatility threshold** — need `np.nanstd() >= 0.05` over the 10-second window before `eval_second=30`. A flat array at 0.50 won't trigger. Use oscillating prices (e.g. alternating 0.55/0.45 or similar) in the window `[20:31]` to produce std dev ≈ 0.05+.
- **`entry_second` key naming** — S2's signal_data should use `entry_second` (generic) rather than `eval_second` for the backtest bridge. But also include `eval_second` for strategy-specific metadata. The adapter fix should look for `entry_second` first, falling back to `reversion_second`, then 0.
