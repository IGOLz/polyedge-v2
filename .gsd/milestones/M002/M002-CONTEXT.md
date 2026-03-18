# M002: Unified Strategy Reports

**Gathered:** 2026-03-18
**Status:** In progress

## Why This Milestone

M001 delivered a shared strategy framework where the same strategy definition runs in both backtest and live trading. But the two sides produce completely different output:

- **Analysis backtest** → CSV/markdown via `engine.save_module_results()` with 20 metrics (win_rate, sharpe, sortino, drawdown, profit_factor, etc.)
- **Trading bot** → `bot_trades` DB rows + lightweight `get_bot_stats()` (total_trades, wins, losses, pnl, roi) logged to bot_logs

An agent comparing backtest vs live performance today would need to parse completely different formats and compute missing metrics.

## User-Visible Outcome

- Both analysis backtest and trading bot produce per-strategy reports in identical JSON + Markdown format
- An agent can load `reports/backtest/S1.json` and `reports/live/S1.json` and compare field-by-field
- The trading bot automatically generates and updates reports on a schedule
- `python -m analysis.backtest_strategies --strategy S1` generates reports in the shared format alongside existing output

## Scope

### In Scope
- `shared/strategies/report.py` — StrategyReport dataclass, JSON/Markdown serialization
- Modify `analysis/backtest_strategies.py` to emit shared reports
- `trading/report.py` — query bot_trades, compute equivalent metrics, generate shared reports
- Wire report generation into trading bot's periodic loop
- Verification

### Out of Scope
- Changing existing engine output (CSV, best-configs)
- Agent-side comparison tooling
- Historical report versioning
- Dashboard or UI
