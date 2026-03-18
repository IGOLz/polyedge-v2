# Creating a New Strategy

This folder is a copy-and-customize template. Follow the steps below to add a
new strategy to the framework.

## 1. Copy the TEMPLATE folder

```bash
cp -r src/shared/strategies/TEMPLATE src/shared/strategies/S3
```

Replace `S3` with the next available strategy ID.

## 2. Rename classes

| File | Old name | New name |
|---|---|---|
| `config.py` | `TemplateConfig` | `S3Config` |
| `strategy.py` | `TemplateStrategy` | `S3Strategy` |

Update the import in `strategy.py`:

```python
from shared.strategies.S3.config import S3Config
```

## 3. Update `get_default_config()`

In `config.py`, change:

```python
return S3Config(
    strategy_id="S3",
    strategy_name="S3_my_strategy",
)
```

## 4. Replace example config fields

Remove `example_threshold`, `example_window_seconds`, and `example_min_spread`.
Add your strategy's real parameters with sensible defaults:

```python
@dataclass
class S3Config(StrategyConfig):
    lookback_seconds: int = 20
    entry_threshold: float = 0.40
    volatility_floor: float = 0.03
```

## 5. Implement `evaluate()`

The `evaluate()` method is the core of your strategy. It must follow this
contract:

- **Pure function:** No side effects, no async, no database access.
- **Return type:** `Signal | None` — return a `Signal` when entry conditions
  are met, `None` otherwise.
- **Never raise** on NaN-heavy, flat, or insufficient data — just return `None`.

The method receives a `MarketSnapshot` with:
- `prices`: numpy array indexed by elapsed second (NaN for missing ticks)
- `total_seconds`: total market duration
- `elapsed_seconds`: current position in the market
- `metadata`: dict with asset info, hour, etc.

### Signal construction

```python
return Signal(
    direction="Up",  # or "Down"
    strategy_name=cfg.strategy_name,
    entry_price=entry_price,
    signal_data={
        "entry_second": entry_second,  # canonical key — see D010
        "your_metric": value,
    },
)
```

> **Important (D010):** Use `entry_second` as the canonical key in
> `signal_data` for the second at which the strategy wants to enter. The
> backtest adapter's Signal→Trade bridge reads this key first, falling back to
> `reversion_second` then `0`.

## 6. Add `get_param_grid()` for parameter optimization

All strategies should define a parameter grid for optimization, even if it starts empty.

Add a `get_param_grid()` function to your `config.py`:

```python
def get_param_grid() -> dict[str, list]:
    """Return parameter ranges for grid-search optimization."""
    return {
        "lookback_seconds": [10, 20, 30],
        "entry_threshold": [0.30, 0.40, 0.50],
    }
```

The optimizer generates the Cartesian product of all parameter values,
instantiates your strategy with each combination, and ranks the results.

## 7. Verify

No registration is needed — `discover_strategies()` auto-discovers your
strategy by scanning `shared/strategies/*/strategy.py` for `BaseStrategy`
subclasses. Just make sure your folder contains `strategy.py` with a class
that inherits from `BaseStrategy`.

```bash
# Check discovery
cd src && PYTHONPATH=. python3 -c \
  "from shared.strategies.registry import discover_strategies; \
   d = discover_strategies(); assert 'S3' in d; print('OK')"

# Run regression suite
cd src && PYTHONPATH=. python3 scripts/parity_test.py
```

## File checklist

```
src/shared/strategies/S3/
├── __init__.py       # empty (required for Python package)
├── config.py         # S3Config(StrategyConfig) + get_default_config()
├── strategy.py       # S3Strategy(BaseStrategy) + evaluate()
└── README.md         # (optional) strategy-specific notes
```
