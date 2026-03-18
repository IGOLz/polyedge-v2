# T01: Trade dataclass extension and test infrastructure setup

**Description:** Extend the Trade dataclass with an exit_reason field to distinguish between stop loss, take profit, and hold-to-resolution exits. Create the tests directory structure required for unit testing the SL/TP engine. This task establishes the foundational contract and test infrastructure that subsequent tasks will build upon.

**Context from slice goal:** Engine must simulate early exits when stop loss or take profit thresholds are hit. The Trade dataclass needs a new field to capture whether a trade exited via SL, TP, or held to market resolution. The exit_reason field must default to 'resolution' for backward compatibility with existing code that doesn't provide SL/TP parameters.

**Estimated duration:** 20m

## Steps

1. **Add exit_reason field to Trade dataclass** — Open `src/analysis/backtest/engine.py`, locate the Trade dataclass definition, add `exit_reason: str = 'resolution'` as a new field. Ensure it comes after existing fields and has the default value to maintain backward compatibility with existing Trade instantiations throughout the codebase.

2. **Create tests directory structure** — Create `src/tests/` directory and add empty `src/tests/__init__.py` file for pytest discovery. This directory doesn't exist yet per research doc constraints.

3. **Create test file skeleton** — Create `src/tests/test_sl_tp_engine.py` with:
   - pytest imports
   - numpy imports for synthetic price arrays
   - fixture for creating synthetic MarketSnapshot objects with controlled price movements
   - placeholder test function structure (tests will be filled in T03)
   - docstring explaining test coverage goals (Up/Down × SL/TP × hit/miss)

4. **Verify backward compatibility** — Run the verification command from task plan to ensure Trade objects can be created without specifying exit_reason and default to 'resolution'. Import Trade in Python REPL, instantiate with existing parameters (no exit_reason), assert default value is correct.

5. **Verify test infrastructure** — Run `cd src && PYTHONPATH=. python3 -m pytest tests/ -v --collect-only` to confirm pytest discovers the new test directory and can import the test file (even if no tests exist yet).

## Must-Haves

- Trade dataclass in `src/analysis/backtest/engine.py` has new field: `exit_reason: str = 'resolution'`
- Field positioned after existing fields in dataclass definition
- Default value 'resolution' ensures backward compatibility with existing code
- `src/tests/` directory created with `__init__.py` for pytest discovery
- `src/tests/test_sl_tp_engine.py` exists with imports and fixture skeleton
- Verification command confirms Trade instantiation works without specifying exit_reason

## Verification

Run these commands in sequence:

```bash
# Verify Trade dataclass has exit_reason field with correct default
cd src && python3 -c "from analysis.backtest.engine import Trade; t = Trade(market_id='test', direction='Up', entry_price=0.50, exit_price=0.60, entered_at=0, exited_at=300, pnl=0.1, trade_amount=100.0); assert t.exit_reason == 'resolution'; print('✓ Trade.exit_reason defaults to resolution')"

# Verify pytest discovers test directory
cd src && PYTHONPATH=. python3 -m pytest tests/ -v --collect-only

# Verify test file imports successfully
cd src && python3 -c "import tests.test_sl_tp_engine; print('✓ Test file imports successfully')"
```

All three commands must succeed with exit code 0.

## Inputs

- Existing Trade dataclass definition in `src/analysis/backtest/engine.py`
- Python 3.x with pytest available (assumed from existing codebase)
- numpy available (used throughout backtest engine)

## Expected Output

**Files created:**
- `src/tests/__init__.py` — Empty file enabling pytest discovery
- `src/tests/test_sl_tp_engine.py` — Test skeleton with structure:
  ```python
  """Unit tests for stop loss and take profit engine simulation.
  
  Tests cover:
  - Up bet SL hit (price drops below threshold)
  - Up bet TP hit (price rises above threshold)
  - Down bet SL hit (price rises above inverted threshold)
  - Down bet TP hit (price drops below inverted threshold)
  - No threshold hit (hold to resolution)
  - NaN price handling
  - Both SL and TP hit in same second (SL priority)
  - PnL calculation correctness
  """
  
  import pytest
  import numpy as np
  from analysis.backtest.engine import Trade, simulate_sl_tp_exit, make_trade
  from shared.types import MarketSnapshot
  
  @pytest.fixture
  def synthetic_market():
      """Create a MarketSnapshot with controlled price movement for testing."""
      # TODO: Implement in T03
      pass
  
  # Test functions will be added in T03
  ```

**Files modified:**
- `src/analysis/backtest/engine.py` — Trade dataclass extended with one new line:
  ```python
  @dataclass
  class Trade:
      market_id: str
      direction: str
      entry_price: float
      exit_price: float
      entered_at: int
      exited_at: int
      pnl: float
      trade_amount: float
      exit_reason: str = 'resolution'  # NEW: 'sl', 'tp', or 'resolution'
  ```

**Verification output:**
- Trade instantiation command prints "✓ Trade.exit_reason defaults to resolution"
- pytest collect-only shows test directory discovered (even if 0 tests collected)
- Test file import succeeds with "✓ Test file imports successfully"

## Observability Impact

**New signals introduced:**
- Trade.exit_reason field visible in all Trade objects created going forward
- Field has three possible values: 'sl' (stop loss hit), 'tp' (take profit hit), 'resolution' (held to market close)
- Default value 'resolution' maintains semantic compatibility with existing behavior

**Diagnostic value:**
- Future agents can inspect any Trade object and immediately see how it exited
- Aggregation by exit_reason (in S04) will show portfolio-level statistics: what percentage of trades hit SL vs TP vs resolution
- Filtering trades by exit_reason enables analysis of whether SL/TP thresholds are calibrated correctly

**State inspection:**
- Trade objects are dataclasses — easily inspectable in REPL with `print(trade)` or `vars(trade)`
- exit_reason is a plain string — no parsing required, can be used directly in pandas groupby or SQL WHERE clauses
- No additional logging infrastructure needed — field presence is self-documenting

**Failure modes made visible:**
- If exit_reason has unexpected value (not 'sl'/'tp'/'resolution'), bug in simulator immediately obvious
- Missing exit_reason field → AttributeError with clear traceback pointing to Trade instantiation
- Default value ensures old code without SL/TP continues working and reports 'resolution' correctly
