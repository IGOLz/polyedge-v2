# M002: Unified Strategy Reports — Research

**Date:** 2026-03-18

## Summary

M002 is a well-scoped, largely completed milestone. All implementation code already exists in commit `777a474` on a detached work branch, including: (1) `shared/strategies/report.py` — a `StrategyReport` dataclass with 20+ metrics, JSON/Markdown serialization, `from_json()` round-trip, and a `from_metrics()` factory; (2) modifications to `analysis/backtest_strategies.py` adding `_generate_reports()` which produces per-strategy `{SID}.json` and `{SID}.md` in `reports/backtest/`; (3) `trading/report.py` — an async module that queries `bot_trades`, computes the full engine-parity metric set via `compute_live_metrics()`, and generates reports in `reports/live/`; (4) `trading/main.py` already has `strategy_report_loop()` wired into the bot's event loop (hourly, 5min offset). A 47-check verification script (`scripts/verify_reports.py`) is also complete.

The core design decision is excellent: both contexts produce `StrategyReport` objects with identical field sets matching `engine.compute_metrics()` output. The 20 metric fields (win_rate, sharpe, sortino, drawdown, profit_factor, quarterly PnL, robustness, consistency) are computed identically in both `engine.compute_metrics` (backtest, using `Trade` dataclass objects) and `compute_live_metrics` (live, using `bot_trades` DB rows). An agent can load `S1.json` from either context and compare field-for-field.

The remaining work is integration: the code in `777a474` needs to be merged/applied to the working tree, and the dependency chain verified — specifically, `shared/strategies/report.py` doesn't exist on disk yet (nor do `base.py`, `registry.py`, S1/, S2/, TEMPLATE/ — these are M001 deliverables that exist in the same branch but aren't on the current HEAD). The actual coding is done; what remains is assembly, verification, and validation.

## Recommendation

Treat this as a **merge + verify** milestone, not a build-from-scratch effort. The implementation in `777a474` is complete and well-structured. The work should be:

1. **Ensure M001 foundation is on disk** — `base.py`, `registry.py`, S1/, S2/, TEMPLATE/ must exist since `report.py` and all consumers import from `shared.strategies`
2. **Apply `shared/strategies/report.py`** — the core new file (310 lines)
3. **Apply the backtest adapter changes** — `_generate_reports()` addition to `backtest_strategies.py` (~70 lines added)
4. **Verify `trading/report.py` and `trading/main.py`** — already on disk and in HEAD, just need the `report.py` dependency to exist
5. **Run `verify_reports.py`** — 47 checks covering imports, construction, JSON round-trip, markdown, live metrics parity, edge cases

## Implementation Landscape

### Key Files

- `src/shared/strategies/report.py` — **New file, core deliverable.** `StrategyReport` dataclass with `from_metrics()`, `from_json()`, `to_json()`, `to_markdown()`. 310 lines. No external deps beyond stdlib + dataclasses.
- `src/shared/strategies/__init__.py` — Already updated to import `StrategyReport` from `.report`. Exists on disk. No further changes needed.
- `src/analysis/backtest_strategies.py` — Needs `_generate_reports()` function added (~70 lines). Already imports `StrategyReport`. Produces `reports/backtest/{SID}.json` and `{SID}.md` alongside existing CSV output.
- `src/trading/report.py` — **Already on disk and in git HEAD.** 379 lines. Queries `bot_trades`, computes `compute_live_metrics()` (parity with `engine.compute_metrics`), generates `reports/live/{SID}.json|.md`. Async.
- `src/trading/main.py` — **Already on disk and in git HEAD.** `strategy_report_loop()` wired in, calls `generate_live_reports()` hourly.
- `src/analysis/backtest/engine.py` — Existing, unmodified. Defines `Trade`, `compute_metrics()`, `save_module_results()`. The 20-field metrics dict is the schema source of truth that `StrategyReport` mirrors.
- `src/scripts/verify_reports.py` — **New file.** 264 lines, 47 checks. Tests imports, construction, JSON round-trip, markdown output, field parity between backtest and live, edge cases (empty trades, single trade).

### Dependency Chain

```
shared/strategies/base.py       ← M001, must exist
shared/strategies/registry.py   ← M001, must exist  
shared/strategies/report.py     ← M002, NEW
shared/strategies/__init__.py   ← Already updated, imports all three
    ↓
analysis/backtest_strategies.py ← M002, adds _generate_reports()
trading/report.py               ← M002, already on disk
trading/main.py                 ← M002, already wired
    ↓
scripts/verify_reports.py       ← M002, verification
```

### Build Order

1. **Verify M001 foundation** — Confirm `base.py`, `registry.py`, S1/, S2/ are on disk. If not, they need to be applied from `777a474` first since `report.py` imports sit in `__init__.py` alongside `base` and `registry` imports.
2. **Create `shared/strategies/report.py`** — Pure dataclass + serialization, zero runtime deps. This unblocks everything else.
3. **Update `analysis/backtest_strategies.py`** — Add `_generate_reports()` and the call in `main()`. Depends on `StrategyReport` being importable.
4. **Verify `trading/report.py` imports work** — Already on disk, just needs `report.py` to exist. No code changes needed.
5. **Deploy `scripts/verify_reports.py`** — Run the 47-check suite. This is the definitive validation.

### Verification Approach

Primary verification:
```bash
cd src && PYTHONPATH=. python3 scripts/verify_reports.py   # 47 checks
```

The verification script covers:
- Import checks (StrategyReport from both `shared.strategies.report` and `shared.strategies`)
- Construction from metrics dict (field mapping, all 20+ fields)
- JSON round-trip (write → read → compare)
- Markdown generation (title, context, metrics, config block)
- Live vs backtest field set parity (symmetric_difference check)
- Trade record handling (dataclass objects and dicts)
- `compute_live_metrics` field parity with `engine.compute_metrics`
- Edge cases (empty trades, single trade)

Supplementary:
```bash
cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"
cd src && PYTHONPATH=. python3 -c "from shared.strategies import StrategyReport; print(StrategyReport.__dataclass_fields__.keys())"
```

## Constraints

- **M001 must be on disk first.** The `shared/strategies/__init__.py` imports `base`, `registry`, and `report` in one block. If `base.py` or `registry.py` are missing, the import fails before `report` is even reached. All M001 strategy files exist in `777a474` but not on the current HEAD.
- **`engine.compute_metrics` field set is the schema contract.** Both `StrategyReport.from_metrics()` and `compute_live_metrics()` must produce/consume the exact same 20 keys. Any field added to `engine.py` must be mirrored in both places.
- **`trading/report.py` is async** (uses `asyncpg` via `shared.db`). The verification script handles this by not calling `generate_live_reports` directly — it only tests `compute_live_metrics` (sync) and import availability.
- **`src/core/` must not be modified** (R010). This milestone doesn't touch core.
- **Existing engine output preserved** (per scope). `save_module_results()` still produces CSV/best-configs/markdown. Reports are additive output in `reports/` subdirectory.

## Common Pitfalls

- **`from_metrics` signature mismatch** — The backtest adapter passes `trades` as a positional arg (`from_metrics(metrics, trades, ...)`), while trading sets `report.trades = trade_records` after construction. This works because `from_metrics` has `trades: list | None = None`, but any refactor must preserve the optional positional parameter.
- **`_strategy_id()` mapping in trading/report.py** — Live trades have `strategy_name` like `"M3_spike_reversion"` (legacy names from before M001 renaming). The `_strategy_id()` function maps `S1_*` → `S1`, but falls back to full name for unrecognized prefixes. Legacy names will produce report files named after the full strategy name, not the `S1`/`S2` convention.
- **Empty trades in live context** — If no resolved trades exist in `bot_trades`, `generate_live_reports` returns `[]` silently (logged but no files). This is correct behavior but agents should handle missing report files.
- **`py_clob_client` mock in verify script** — The verification script mocks `py_clob_client` modules to avoid requiring the trading dependency chain. This is necessary because `trading.report` → `shared.db` → asyncpg, and the full stack isn't available in a test environment without Docker.

## Open Risks

- **Stale working tree** — The code on disk has `trading/report.py` and `trading/main.py` already (from HEAD), but `shared/strategies/report.py` doesn't exist. The `__init__.py` will fail to import until all three modules (`base`, `registry`, `report`) are present. The build order must strictly create M001 foundation files before M002 files.
- **Metric formula drift** — `compute_live_metrics()` in `trading/report.py` is a manual re-implementation of `engine.compute_metrics()` for dict-based trade records (vs `Trade` dataclass). If engine formulas change, they must be updated in both places. A future DRY improvement could extract shared math, but that's out of scope.