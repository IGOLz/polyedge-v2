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
| D008 | M003 | scope | Old S1/S2 strategies | Delete and replace with research-backed strategies (supersedes D005) | User wants clean slate; old strategies were disposable proof-of-concept tenants. Research identified 7 viable strategy families for 5-min crypto prediction markets. | No |
| D009 | M003 | arch | Fee model for backtesting | Polymarket dynamic fee formula: `baseRate × min(price, 1-price)` | Flat 2% doesn't reflect real Polymarket fee structure for short-term crypto markets. Dynamic fees peak at ~3.15% near 50/50 prices and are lower at extreme prices. Base rate configurable. | Yes — if Polymarket changes fee structure |
| D010 | M003 | arch | Slippage modeling | Configurable entry price penalty (default ~1 cent) | Price penalty simulates realistic execution in short-duration markets where the fill price differs from the price the strategy detected. More honest than zero slippage. | Yes — if order book data becomes available for more sophisticated modeling |
| D011 | M003 | scope | Data sources for strategies | Polymarket tick data only (no external exchange feeds) | User confirmed no Binance/Coinbase data available. Latency arbitrage strategies are excluded; all strategies work from the tick data core already collects. | Yes — if external feeds are added |
| D012 | M004 | arch | Stop loss and take profit representation | Absolute price thresholds (not relative offsets) | Simpler to reason about; matches user's example ("sell at 0.70"); relative offsets can be added later if needed | Yes — if relative offsets prove more useful |
| D013 | M004 | arch | SL/TP parameter ownership | Strategy-specific (each declares own ranges in get_param_grid) | Different entry patterns need different exit thresholds; strategy-specific gives more flexibility than universal engine params | Yes — if universal ranges prove sufficient |
| D014 | M004 | arch | Invalid parameter combination handling | Skip during grid generation | Combinations like SL > TP for Up bets are nonsensical; skipping avoids wasted backtest runs | No |
