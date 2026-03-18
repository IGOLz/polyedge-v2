# S01: Apply unified report implementation and verify — UAT

**Milestone:** M002
**Written:** 2026-03-18

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All verification is against in-process Python objects, serialized files, and import chains — no running server or database required. The 47-check script uses mocked data and exercises the full pipeline.

## Preconditions

- Working directory is the M002 worktree with `src/` fully populated (41 files)
- Python 3.10+ available
- No external services required (TimescaleDB not needed — verification uses mocks)
- No symlinks in `src/` (all converted to real files)

## Smoke Test

```bash
cd src && PYTHONPATH=. python3 -c "from shared.strategies.report import StrategyReport; print('OK')"
```
Expected: prints `OK` with exit code 0.

## Test Cases

### 1. Full 47-check verification suite

1. Run `cd src && PYTHONPATH=. python3 scripts/verify_reports.py`
2. **Expected:** Output ends with `=== Results: 47 passed, 0 failed ===` and exit code 0

### 2. StrategyReport construction from metrics dict

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 50, 'wins': 30, 'losses': 20, 'total_pnl': 12.5,
              'win_rate_pct': 60.0, 'sharpe_ratio': 0.85, 'ranking_score': 75.0}
   r = StrategyReport.from_metrics('S1', 'Spike Reversion', metrics, context='backtest')
   print(r.strategy_id, r.total_bets, r.win_rate_pct, r.context)
   "
   ```
2. **Expected:** `S1 50 60.0 backtest`

### 3. JSON round-trip preserves all fields

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import tempfile, os
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 50, 'wins': 30, 'losses': 20, 'total_pnl': 12.5,
              'win_rate_pct': 60.0, 'sharpe_ratio': 0.85, 'ranking_score': 75.0}
   r = StrategyReport.from_metrics('S1', 'Spike', metrics, context='backtest')
   p = os.path.join(tempfile.mkdtemp(), 'test.json')
   r.to_json(p)
   r2 = StrategyReport.from_json(p)
   print(r.strategy_id == r2.strategy_id, r.total_pnl == r2.total_pnl, r.context == r2.context)
   "
   ```
2. **Expected:** `True True True`

### 4. Markdown generation includes all sections

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import tempfile, os
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 50, 'wins': 30, 'losses': 20, 'total_pnl': 12.5,
              'win_rate_pct': 60.0, 'sharpe_ratio': 0.85, 'ranking_score': 75.0}
   r = StrategyReport.from_metrics('S1', 'Spike', metrics, context='backtest')
   p = os.path.join(tempfile.mkdtemp(), 'test.md')
   r.to_markdown(p)
   content = open(p).read()
   checks = ['S1' in content, 'backtest' in content, '60.0' in content, '12.5' in content, 'Sharpe' in content]
   print(all(checks), len(content))
   "
   ```
2. **Expected:** `True` followed by a positive character count (e.g., `True 450`)

### 5. Backtest and live field sets are identical

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 10, 'wins': 5, 'losses': 5, 'total_pnl': 1.0,
              'win_rate_pct': 50.0, 'sharpe_ratio': 0.5, 'ranking_score': 50.0}
   bt = StrategyReport.from_metrics('S1', 'X', metrics, context='backtest')
   lv = StrategyReport.from_metrics('S1', 'X', metrics, context='live')
   bt_fields = set(bt.to_dict().keys())
   lv_fields = set(lv.to_dict().keys())
   print('parity:', bt_fields == lv_fields, 'diff:', bt_fields.symmetric_difference(lv_fields))
   "
   ```
2. **Expected:** `parity: True diff: set()`

### 6. StrategyReport re-export from package __init__

1. Run `cd src && PYTHONPATH=. python3 -c "from shared.strategies import StrategyReport; print(sorted(StrategyReport.__dataclass_fields__.keys()))"`
2. **Expected:** List of 29 field names including `strategy_id`, `total_pnl`, `sharpe_ratio`, `context`, `win_rate_pct`

### 7. Analysis adapter has _generate_reports

1. Run `grep -c '_generate_reports' src/analysis/backtest_strategies.py`
2. **Expected:** At least 2 (definition + call)

### 8. Trading report module exports

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   import sys; sys.modules['py_clob_client'] = type(sys)('mock')
   from trading.report import compute_live_metrics, generate_live_reports
   print('compute_live_metrics:', callable(compute_live_metrics))
   print('generate_live_reports:', callable(generate_live_reports))
   "
   ```
2. **Expected:** Both print `True`

## Edge Cases

### Empty trades (zero-bet scenario)

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0,
              'win_rate_pct': 0.0, 'sharpe_ratio': 0.0, 'ranking_score': 0.0}
   r = StrategyReport.from_metrics('S1', 'X', metrics, context='backtest')
   print(r.total_bets, r.total_pnl)
   "
   ```
2. **Expected:** `0 0.0`

### Single trade scenario

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.report import StrategyReport
   metrics = {'total_bets': 1, 'wins': 1, 'losses': 0, 'total_pnl': 5.0,
              'win_rate_pct': 100.0, 'sharpe_ratio': 0.0, 'ranking_score': 80.0}
   r = StrategyReport.from_metrics('S1', 'X', metrics, context='backtest')
   print(r.total_bets, r.wins)
   "
   ```
2. **Expected:** `1 1`

### Minimal construction (defaults)

1. Run:
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from shared.strategies.report import StrategyReport
   r = StrategyReport(strategy_id='test', strategy_name='X', context='backtest')
   d = r.to_dict()
   print(d['strategy_id'], type(d))
   "
   ```
2. **Expected:** `test <class 'dict'>`

## Failure Signals

- Import errors (`ModuleNotFoundError`) — M001 foundation files missing or `__init__.py` broken
- `verify_reports.py` exits non-zero — specific check name printed with ✗ marker
- Field parity mismatch — `symmetric_difference` returns non-empty set
- JSON round-trip failure — loaded fields don't match original
- `py_clob_client` import error from `trading/report.py` — mock not intercepting

## Requirements Proved By This UAT

- R001 — One strategy definition produces reports in both contexts with identical schemas
- R002 — Strategy folder naming (S1, S2) flows through to report file paths
- R008 — Registry-discovered strategy IDs are used as report identifiers

## Not Proven By This UAT

- Live database integration: `compute_live_metrics()` with real `bot_trades` data (requires TimescaleDB)
- Report file generation in `reports/backtest/` and `reports/live/` directories (backtest engine not exercised end-to-end)
- `strategy_report_loop()` hourly execution in trading bot event loop (requires running bot)
- Report file comparison tooling (agent-side, deferred)

## Notes for Tester

- All tests run in-process with no external dependencies. Python 3.10+ and a populated `src/` tree are the only requirements.
- The `trading/report.py` module imports `py_clob_client` transitively — the verification script handles this with `sys.modules` mocking. If running test case 8 manually, include the mock line.
- `verify_reports.py` creates temporary files in `/tmp` for JSON/Markdown round-trip tests and cleans up after itself.
