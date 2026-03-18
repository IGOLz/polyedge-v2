# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? |
|---|------|-------|----------|--------|-----------|------------|
| D001 | M001 | arch | Strategy evaluate function sync vs async | Synchronous (no await) | Must work in both async trading and sync analysis contexts; trading can call sync functions from async code trivially | No |
| D002 | M001 | arch | Time axis for strategy data | Elapsed seconds from market start | Fixes the tick-index-as-seconds bug; matches how analysis backtest already works; unambiguous unit | No |
| D003 | M001 | convention | Strategy naming scheme | S1, S2, S3... in `shared/strategies/` | User requested; simple, sequential, folder-per-strategy | Yes — if naming feels wrong after use |
| D004 | M001 | arch | MarketSnapshot format | Numpy array indexed by elapsed second + metadata dict | Matches existing backtest data_loader format; efficient for numpy operations in strategies; trading adapter builds it from tick list | No |
| D005 | M001 | scope | Existing strategy params | Port as-is, don't optimize | User confirmed all current strategies are disposable; framework matters, not the specific params | No |
| D006 | M001 | arch | Signal backward compatibility | Shared Signal includes all fields trading executor expects | Executor is not being modified; Signal must be a superset of current shape | No |
| D007 | M001 | scope | Old analysis code (analysis/main.py, analysis/strategies/) | Leave in place, don't migrate | Statistical analysis and old-style backtests aren't strategies; they can coexist and be cleaned up later | Yes — when user wants cleanup |
