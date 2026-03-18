"""S01 verification — run from src/ directory."""
import sys
import numpy as np


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if not condition:
        sys.exit(1)


print("=== S01 Verification ===\n")

# 1. Import check
print("1. Imports")
from shared.strategies import (
    BaseStrategy,
    StrategyConfig,
    MarketSnapshot,
    Signal,
    discover_strategies,
    get_strategy,
)

check("All public API importable", True)

# 2. Registry discovers S1
print("\n2. Registry")
strategies = discover_strategies()
check("discover_strategies() finds S1", "S1" in strategies)
s1 = get_strategy("S1")
check("get_strategy('S1') returns instance", isinstance(s1, BaseStrategy))
check("S1 config.strategy_id == 'S1'", s1.config.strategy_id == "S1")
check(
    "S1 config.strategy_name == 'S1_spike_reversion'",
    s1.config.strategy_name == "S1_spike_reversion",
)

# 3. Spike-up → Down signal (contrarian)
print("\n3. Spike detection — up spike")
prices = np.full(300, 0.50)
prices[3:8] = 0.85  # spike up in detection window (>= 0.80 threshold)
# After spike, prices drop partially but stay high so DOWN entry_price ≤ 0.35
# entry_price = 1.0 - up_price, so up_price ≥ 0.65 → entry ≤ 0.35
# Reversion: (0.85 - 0.75) / 0.85 ≈ 0.118 ≥ 0.10 threshold
prices[8:15] = 0.75
snap = MarketSnapshot(
    market_id="test_up",
    market_type="btc_5m",
    prices=prices,
    total_seconds=300,
    elapsed_seconds=30.0,
    metadata={"asset": "btc"},
)
result = s1.evaluate(snap)
check("Returns a Signal (not None)", result is not None)
if result:
    check("Direction is 'Down' (contrarian to up-spike)", result.direction == "Down")
    check("strategy_name set", result.strategy_name == "S1_spike_reversion")
    check("entry_price is a float", isinstance(result.entry_price, (int, float)))

# 4. No spike → None
print("\n4. No spike — flat prices")
flat_prices = np.full(300, 0.50)
snap_flat = MarketSnapshot(
    market_id="test_flat",
    market_type="btc_5m",
    prices=flat_prices,
    total_seconds=300,
    elapsed_seconds=30.0,
    metadata={"asset": "btc"},
)
result_flat = s1.evaluate(snap_flat)
check("Returns None for flat prices", result_flat is None)

# 5. NaN resilience
print("\n5. NaN handling")
nan_prices = np.full(300, np.nan)
snap_nan = MarketSnapshot(
    market_id="test_nan",
    market_type="btc_5m",
    prices=nan_prices,
    total_seconds=300,
    elapsed_seconds=30.0,
    metadata={"asset": "btc"},
)
result_nan = s1.evaluate(snap_nan)
check("All-NaN returns None (no crash)", result_nan is None)

# 6. Signal field completeness (D006)
print("\n6. Signal backward compatibility")
sig = Signal(direction="Up", strategy_name="test", entry_price=0.5)
check("signal.locked_shares defaults to 0", sig.locked_shares == 0)
check("signal.locked_cost defaults to 0.0", sig.locked_cost == 0.0)
check("signal.locked_balance defaults to 0.0", sig.locked_balance == 0.0)
check("signal.locked_bet_size defaults to 0.0", sig.locked_bet_size == 0.0)
check("signal.signal_data defaults to {}", sig.signal_data == {})
check("signal.confidence_multiplier defaults to 1.0", sig.confidence_multiplier == 1.0)
check("signal.created_at is set", sig.created_at is not None)

# 7. Import isolation — no forbidden imports
print("\n7. Import isolation")
import ast
import pathlib

strategies_dir = pathlib.Path(__file__).parent.parent / "shared" / "strategies"
forbidden = []
for py_file in strategies_dir.rglob("*.py"):
    tree = ast.parse(py_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [module]
            )
            for name in names:
                if name and any(
                    name.startswith(p) for p in ("trading", "analysis", "core")
                ):
                    forbidden.append(f"{py_file.name}: {name}")
check(f"No forbidden imports (found: {forbidden})", len(forbidden) == 0)

print("\n=== All S01 checks passed ===")
