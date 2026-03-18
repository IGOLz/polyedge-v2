---
id: T01
parent: S04
milestone: M001
provides:
  - S2 volatility strategy (shared/strategies/S2/) — pure, synchronous, numpy-only
  - Generic entry_second fallback in backtest adapter Signal→Trade bridge
key_files:
  - src/shared/strategies/S2/__init__.py
  - src/shared/strategies/S2/config.py
  - src/shared/strategies/S2/strategy.py
  - src/analysis/backtest_strategies.py
key_decisions:
  - S2 uses np.nanstd() with ddof=0 (population std), matching both the M4 trading implementation and analysis backtest convention
  - Backtest adapter uses entry_second→reversion_second→0 fallback chain rather than strategy-specific branching
patterns_established:
  - S2 follows the exact S1 directory/class pattern: config.py (dataclass + get_default_config), strategy.py (BaseStrategy subclass), __init__.py (empty)
observability_surfaces:
  - S2 Signal.signal_data includes eval_second, spread, volatility, entry_second, price_at_eval for diagnostic inspection
duration: 8m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T01: Port S2 volatility strategy and fix backtest adapter entry_second

**Created S2 volatility strategy in shared/strategies/S2/ porting M4 detection logic, and fixed backtest adapter entry_second fallback chain**

## What Happened

Created three files in `src/shared/strategies/S2/` following the S1 pattern exactly:
- `__init__.py` (empty)
- `config.py` with `S2Config(StrategyConfig)` dataclass — parameters match M4_CONFIG: eval_second=30, eval_window=2, volatility_window_seconds=10, volatility_threshold=0.05, min_spread=0.05, max_spread=0.50, base_deviation=0.08
- `strategy.py` with `S2Strategy(BaseStrategy)` implementing the pure volatility detection: guard on data length → check price at eval_second → base deviation filter → spread range filter → compute volatility via np.nanstd over 10s window → contrarian direction

Fixed the backtest adapter's Signal→Trade bridge in `analysis/backtest_strategies.py`: changed `signal_data.get('reversion_second', 0)` to `signal_data.get('entry_second', signal_data.get('reversion_second', 0))`. S2 uses `entry_second`, S1 uses `reversion_second`, and the fallback chain handles both without modifying S1.

## Verification

- Registry discovers both S1 and S2 via `discover_strategies()`
- S2 fires correctly on synthetic volatile data (alternating 0.55/0.45 in vol window, 0.60 at eval_second → Down direction, entry 0.40)
- S2 returns None on flat data (all 0.50 — deviation < 0.08)
- verify_s01.py: all 17 checks pass (no regressions)
- verify_s02.py: all 18 checks pass (adapter fix doesn't break S1 pipeline)
- Import isolation verified: no trading/analysis/core imports in S2 files

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `discover_strategies()` asserts S1+S2 | 0 | ✅ pass | 10.9s |
| 2 | S2 synthetic volatility evaluation | 0 | ✅ pass | 2.9s |
| 3 | `scripts/verify_s01.py` (17 checks) | 0 | ✅ pass | 6.0s |
| 4 | `scripts/verify_s02.py` (18 checks) | 0 | ✅ pass | 3.2s |
| 5 | S2 returns None on flat data | 0 | ✅ pass | <1s |
| 6 | Import isolation check (no forbidden imports) | 0 | ✅ pass | <1s |

## Diagnostics

- **Inspect S2 registration:** `cd src && PYTHONPATH=. python3 -c "from shared.strategies import discover_strategies; print(discover_strategies())"`
- **Debug S2 signal on custom data:** Construct a `MarketSnapshot` with desired prices array, call `S2Strategy(get_default_config()).evaluate(snap)`, inspect returned Signal's `signal_data` dict for `spread`, `volatility`, `price_at_eval`.
- **Failure diagnosis:** S2 returns None on any guard failure (insufficient data, NaN at eval_second, deviation < 0.08, spread outside [0.05, 0.50], volatility < 0.05). Guards are ordered and short-circuiting.

## Deviations

None — implementation matched the plan exactly.

## Known Issues

None.

## Files Created/Modified

- `src/shared/strategies/S2/__init__.py` — empty init (auto-discovery pattern)
- `src/shared/strategies/S2/config.py` — S2Config dataclass with M4 parameters + get_default_config()
- `src/shared/strategies/S2/strategy.py` — S2Strategy with pure volatility detection evaluate()
- `src/analysis/backtest_strategies.py` — entry_second→reversion_second→0 fallback chain (line 81-83)
