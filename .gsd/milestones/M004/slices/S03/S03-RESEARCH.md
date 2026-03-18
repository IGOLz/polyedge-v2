# S03 — Grid Search Orchestrator Research

**Date:** 2026-03-18

## Summary

S03 wires together S01's parameter grids (which include stop_loss and take_profit keys) with S02's SL/TP exit engine into the optimize.py grid search orchestrator. The core challenge is that stop_loss and take_profit are NOT fields of strategy config dataclasses - they're exit parameters that must be passed separately to make_trade().

The implementation splits each parameter combination into strategy_params (fields that exist in the config dataclass) and exit_params (stop_loss, take_profit), passes strategy_params to dataclasses.replace() to build custom configs, and passes exit_params through run_strategy() to make_trade(). Metrics dict gets augmented with SL/TP values so they appear in CSV output.

Current dry-run already works (shows 972 combinations for S1 including SL/TP dimensions). The optimizer will generate 648-1728 combinations per strategy (S01 delivered these grids). No validation logic needed because S01 ensured all grids have valid SL < TP combinations.

## Recommendation

**Targeted changes to optimize.py and backtest_strategies.py with no new abstractions.**

1. In `optimize.py::optimize_strategy()`, introspect the strategy config dataclass to identify which grid parameters are config fields vs exit params, split param_dict accordingly, pass exit_params to run_strategy()

2. In `backtest_strategies.py::run_strategy()`, accept stop_loss=None and take_profit=None parameters, pass them to make_trade() calls, augment metrics dict with SL/TP values before returning

3. No changes to compute_metrics (it doesn't need to know about SL/TP - they're injected into metrics dict after)

4. No changes to Trade dataclass (exit_reason field from S02 is sufficient)

5. No validation logic (S01 grids are pre-validated, bad combinations will naturally rank low)

This approach is minimal, follows existing patterns (dataclasses.replace for config, keyword-only params for make_trade), and preserves all S02 deliverables unchanged.

## Implementation Landscape

### Key Files

- `src/analysis/optimize.py` — optimize_strategy() function generates Cartesian product and orchestrates backtests. Needs to split param_dict into strategy_params and exit_params, pass exit_params to run_strategy.

- `src/analysis/backtest_strategies.py` — run_strategy() function bridges strategy evaluation into engine. Needs to accept stop_loss and take_profit parameters, pass them to make_trade(), and augment metrics dict before returning.

- `src/analysis/backtest/engine.py` — make_trade() already accepts stop_loss and take_profit as keyword-only parameters (S02 deliverable). No changes needed.

- `src/shared/strategies/S1/config.py` (and S2-S7) — get_param_grid() already returns dicts with stop_loss and take_profit keys (S01 deliverable). No changes needed.

### Build Order

**T01: Split parameter dict in optimize.py** — Low risk, pure data transformation.

Introspect strategy config dataclass to identify which param_dict keys are valid config fields. Split into strategy_params and exit_params. Pass strategy_params to dataclasses.replace(), pass exit_params to run_strategy().

Pattern:
```python
config_fields = {f.name for f in dataclasses.fields(type(base_config))}
strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}
exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}
custom_config = dataclasses.replace(base_config, **strategy_params)
trades, metrics = run_strategy(config_label, strategy, markets, 
                                stop_loss=exit_params.get('stop_loss'),
                                take_profit=exit_params.get('take_profit'))
```

Verification: Run dry-run (no market data loaded), verify grid summary prints correctly including SL/TP dimensions.

**T02: Thread SL/TP through run_strategy to make_trade** — Low risk, follows established pattern.

Update run_strategy() signature to accept stop_loss=None and take_profit=None parameters. Update make_trade() call to pass these values.

Pattern:
```python
def run_strategy(
    strategy_id: str,
    strategy,
    markets: list[dict],
    slippage: float = 0.0,
    base_rate: float = 0.063,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> tuple[list[Trade], dict]:
    # ... existing code ...
    trade = make_trade(
        market,
        second_entered,
        signal.entry_price,
        signal.direction,
        slippage=slippage,
        base_rate=base_rate,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
```

Augment metrics dict before returning:
```python
metrics = compute_metrics(trades, config_id=strategy_id)
if stop_loss is not None:
    metrics['stop_loss'] = stop_loss
if take_profit is not None:
    metrics['take_profit'] = take_profit
return trades, metrics
```

Verification: Run full optimize for S1 with market data, verify trades have exit_reason populated correctly (some 'sl', some 'tp', some 'resolution'), verify output CSV includes stop_loss and take_profit columns.

**T03: Update config_label to include SL/TP** — Optional refinement for readability.

Currently config_label includes all param_dict keys (e.g., `S1_entry_window_start=30_..._stop_loss=0.35_take_profit=0.65`). This is already correct because param_dict includes SL/TP from the grid. Verify that labels are readable and that top 10 summary prints show SL/TP values clearly.

If labels are too long, consider truncating or using abbreviated keys (sl/tp instead of stop_loss/take_profit).

Verification: Inspect top 10 summary output, confirm SL/TP values are visible and useful for decision-making.

### Verification Approach

**Smoke test (without full market data load):**
```bash
cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run
# Verify: "Total combinations: 972" (or similar high count including SL/TP dimensions)
# Verify: "stop_loss: [0.35, 0.4, 0.45]" and "take_profit: [0.65, 0.7, 0.75]" in grid summary
```

**Integration test (with market data):**
```bash
cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1
# Verify: Runs 972 backtests without errors
# Verify: Output CSV includes stop_loss and take_profit columns
# Verify: Top 10 summary prints explicit SL/TP values for each ranked combination
# Verify: At least one trade has exit_reason='sl' and one has exit_reason='tp'
```

**CSV output verification:**
```bash
cd src && head results/optimization/Test_optimize_S1_Results.csv
# Check: stop_loss and take_profit columns exist
# Check: Values match the grid (0.35-0.45 for SL, 0.65-0.75 for TP)
```

**Trade-level verification:**
```python
import pandas as pd
df = pd.read_csv('results/optimization/optimize_S1_trades_S1_entry_window_start=30_..._stop_loss=0.35_take_profit=0.65.csv')
print(df['exit_reason'].value_counts())
# Verify: Mix of 'sl', 'tp', 'resolution' values (not all one type)
```

## Constraints

- **Cannot modify S02 deliverables** — Trade dataclass and make_trade() signature are frozen from S02. Any changes to support SL/TP must happen in optimizer and backtest_strategies only.

- **Backward compatibility with strategies without SL/TP** — If a strategy's get_param_grid() returns empty dict or doesn't include stop_loss/take_profit keys, the optimizer should skip it gracefully (already does this - prints "empty dict — skipping").

- **Dry-run must work without market data** — Grid summary calculation and combination count must not require loading markets or evaluating strategies. Current implementation already supports this.

- **Parameter space explosion awareness** — S01 grids range from 648 to 1728 combinations per strategy. Full M004 verification (all 7 strategies) could take significant runtime. S03 should test on S1 only, leaving full sweep for S05 milestone verification.

## Common Pitfalls

- **Passing SL/TP to dataclasses.replace will fail** — stop_loss and take_profit are NOT fields of StrategyConfig subclasses. Attempting `dataclasses.replace(base_config, **param_dict)` where param_dict includes SL/TP will raise TypeError. Solution: Filter param_dict to only include config fields before calling replace.

- **Forgetting to augment metrics dict** — compute_metrics() doesn't know about SL/TP, so they must be added to the metrics dict explicitly in run_strategy() before returning. Otherwise CSV output won't include these columns.

- **None vs missing key semantics** — When a strategy doesn't have SL/TP in its grid, exit_params dict will be empty. Passing stop_loss=None to make_trade() correctly triggers hold-to-resolution logic (S02 behavior). Don't use dict.get() without default=None explicitly.

- **Config label explosion** — Including all parameters in config_label creates very long strings (e.g., `S1_entry_window_start=30_entry_window_end=60_price_low_threshold=0.4_price_high_threshold=0.55_min_deviation=0.05_stop_loss=0.35_take_profit=0.65`). This is acceptable for S03 (max ~20 params × ~10 chars = 200 chars per label), but if labels exceed 255 chars (filesystem limit), truncate or hash them.

- **Metrics dict column ordering** — When building DataFrame from list of metrics dicts, pandas infers column order from first dict. If first combination has different keys than later ones (e.g., missing SL/TP), column order will be inconsistent. Solution: Always add SL/TP keys to metrics dict even if values are None (preserves column presence).

## Open Risks

- **Runtime for full grid search** — S1 has 972 combinations. If each backtest takes ~1 second (load market, evaluate strategy, compute metrics), full S1 optimization = ~16 minutes. This is acceptable. But if all 7 strategies × ~1000 combos each = ~2 hours for full M004. Mitigation: S03 tests S1 only, S05 verification measures actual runtime and adjusts if needed.

- **Market data load time** — Current data_loader.load_all_data() loads all markets into memory. With 972 combinations × N markets per strategy, memory usage could spike. If this causes issues, consider lazy loading or batching. But existing code already does this correctly (markets loaded once, reused for all combinations).

- **SL/TP values in config_label might confuse CSV column alignment** — When config_label includes "stop_loss=0.35", and metrics dict also has stop_loss: 0.35, there's no conflict (different data). But if someone tries to parse config_label to extract SL/TP, they'll duplicate data. Not a problem for S03, but document this for future work.
