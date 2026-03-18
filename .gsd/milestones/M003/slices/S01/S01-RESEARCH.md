# S01 — Research

**Date:** 2026-03-18

## Summary

This slice clears out the disposable proof-of-concept strategies (S1 spike reversion, S2 volatility) and creates scaffolding for 7 new research-backed strategies. After completion, the old strategies are deleted, TEMPLATE is updated to include `get_param_grid()`, and 7 empty strategy folders exist with stub implementations that the registry can discover.

The work is straightforward folder manipulation and file copying. No new architectural patterns are needed — the registry auto-discovery convention already exists, and both old strategies (S1, S2) and the TEMPLATE already demonstrate the required structure. The main deliverable is clean scaffolding that S03 will populate with real logic.

## Recommendation

1. Delete `src/shared/strategies/S1/` and `src/shared/strategies/S2/`
2. Update `src/shared/strategies/TEMPLATE/config.py` to include a skeleton `get_param_grid()` function
3. Update `src/shared/strategies/TEMPLATE/README.md` to reflect the new param grid requirement (it already mentions param grid but should be more prominent)
4. Create 7 new strategy folders by copying TEMPLATE: `S1/` through `S7/`
5. For each new strategy folder, update class names and IDs to match the strategy number and descriptive name from the roadmap
6. Implement stub `evaluate()` methods that return `None` (no signal) with a TODO comment
7. Verify that `discover_strategies()` finds all 7 new strategies

This is light research — known patterns, established codebase conventions, no new technology or risky integration.

## Implementation Landscape

### Key Files

- `src/shared/strategies/S1/` — OLD spike reversion strategy, DELETE
- `src/shared/strategies/S2/` — OLD volatility strategy, DELETE
- `src/shared/strategies/TEMPLATE/config.py` — ADD `get_param_grid()` skeleton
- `src/shared/strategies/TEMPLATE/README.md` — UPDATE to emphasize param grid requirement
- `src/shared/strategies/TEMPLATE/strategy.py` — reference implementation, no changes needed
- `src/shared/strategies/S1/` through `S7/` — NEW strategy folders, copy from TEMPLATE
- `src/shared/strategies/registry.py` — auto-discovery, no changes needed

### Strategy Naming Map

From M003-ROADMAP.md, the 7 new strategies are:

| Folder | Strategy ID | Strategy Name | Description |
|--------|-------------|---------------|-------------|
| `S1/` | S1 | `S1_calibration` | Calibration Mispricing — exploit systematic bias in 50/50 pricing |
| `S2/` | S2 | `S2_momentum` | Early Momentum — detect directional velocity in first 30-60 seconds |
| `S3/` | S3 | `S3_reversion` | Mean Reversion — fade early spikes after partial reversion |
| `S4/` | S4 | `S4_volatility` | Volatility Regime — enter contrarian only under specific vol conditions |
| `S5/` | S5 | `S5_time_phase` | Time-Phase Entry — optimal entry timing based on market phase |
| `S6/` | S6 | `S6_streak` | Streak/Sequence — exploit consecutive same-direction outcomes |
| `S7/` | S7 | `S7_composite` | Composite Ensemble — enter only when 2+ strategies agree |

### Build Order

1. **Delete old strategies first** — removes S1, S2 to make room for clean slate
2. **Update TEMPLATE** — add `get_param_grid()` skeleton so all new strategies inherit the pattern
3. **Create new strategy folders** — copy TEMPLATE to S1-S7, customize IDs and names
4. **Verify discovery** — run `discover_strategies()` to confirm all 7 are found

### Verification Approach

Run from `src/`:

```bash
# Check that old strategies are gone
! test -d src/shared/strategies/S1 || echo "FAIL: S1 still exists"
! test -d src/shared/strategies/S2 || echo "FAIL: S2 still exists"

# Check that new strategies exist
for i in {1..7}; do
  test -d src/shared/strategies/S$i || echo "FAIL: S$i missing"
done

# Check that TEMPLATE has get_param_grid
grep -q "get_param_grid" src/shared/strategies/TEMPLATE/config.py || echo "FAIL: TEMPLATE missing get_param_grid"

# Check registry discovery
PYTHONPATH=. python3 -c "
from shared.strategies.registry import discover_strategies
strategies = discover_strategies()
expected = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE'}
found = set(strategies.keys())
missing = expected - found
extra = found - expected
if missing:
    print(f'FAIL: Missing strategies: {missing}')
    exit(1)
if extra:
    print(f'WARN: Extra strategies: {extra}')
print('PASS: All 7 strategies + TEMPLATE discovered')
"

# Verify each strategy can be instantiated
for i in {1..7}; do
  PYTHONPATH=. python3 -c "
from shared.strategies.registry import get_strategy
s = get_strategy('S$i')
assert s.config.strategy_id == 'S$i', 'ID mismatch'
print(f'PASS: S$i instantiated with name {s.config.strategy_name}')
" || exit 1
done
```

### TEMPLATE Updates

**Add to `config.py`:**

```python
def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for this strategy.

    The optimizer generates the Cartesian product of all parameter values
    and backtests every combination.

    Example:
        return {
            "example_threshold": [0.30, 0.40, 0.50],
            "example_window_seconds": [10, 20, 30],
        }

    Returns:
        Empty dict (no optimization) — replace with real parameters.
    """
    return {}
```

**Update `README.md` section 6** to make param grid non-optional:

Change:
> ## 6. (Optional) Add `get_param_grid()` for parameter optimization

To:
> ## 6. Add `get_param_grid()` for parameter optimization
>
> All strategies should define a parameter grid for optimization, even if it starts empty.

### Per-Strategy Stub Pattern

For each new strategy folder (S1-S7), after copying from TEMPLATE:

1. Rename `TemplateStrategy` → `S{N}Strategy` in `strategy.py`
2. Rename `TemplateConfig` → `S{N}Config` in `config.py`
3. Update `get_default_config()` to return correct `strategy_id` and `strategy_name`
4. Add empty `get_param_grid()` with TODO comment: `# TODO: Define parameter ranges in S03`
5. Keep `evaluate()` returning `None` with comment: `# TODO: Implement in S03`

Example for S1 (Calibration):

```python
# config.py
@dataclass
class S1Config(StrategyConfig):
    """Configuration for Calibration Mispricing strategy."""
    # TODO: Add real parameters in S03
    pass

def get_default_config() -> S1Config:
    return S1Config(
        strategy_id="S1",
        strategy_name="S1_calibration",
    )

def get_param_grid() -> dict[str, list]:
    # TODO: Define parameter ranges in S03
    return {}
```

```python
# strategy.py
class S1Strategy(BaseStrategy):
    """Calibration Mispricing — exploit systematic bias in 50/50 pricing.
    
    TODO: Implement in S03 based on analysis/strategies/strategy_calibration.py
    """
    
    config: S1Config
    
    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        # TODO: Implement calibration mispricing detection in S03
        return None
```

## Constraints

- Must not modify `src/core/` (R010)
- Must not break existing `discover_strategies()` or `get_strategy()` calls
- Must not modify `src/shared/strategies/base.py` or `registry.py` (no contract changes)
- Each strategy folder must be independently discoverable by registry (no hardcoded imports elsewhere)

## Common Pitfalls

- **Forgetting `__init__.py`** — Python won't recognize the folder as a package. All 7 new folders need empty `__init__.py` files.
- **Class name collisions** — If multiple strategies use `TemplateStrategy`, registry will only find the last one. Must rename to `S1Strategy`, `S2Strategy`, etc.
- **Import paths** — After renaming, `strategy.py` must import from the correct config module (e.g., `from shared.strategies.S1.config import S1Config`)
