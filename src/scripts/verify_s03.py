"""S03 verification — trading adapter pipeline (no DB required).

Run from src/ directory:
    cd src && PYTHONPATH=. python3 scripts/verify_s03.py
"""
import sys
import os

# ── Mock external dependencies before any trading imports ───────────
# py_clob_client is a runtime trading dependency not installed in dev.
# trading.config has side effects on import (reads env).  shared.db
# needs asyncpg.  colorama is optional but imported by trading.utils.
from unittest.mock import MagicMock, AsyncMock

for mod in [
    "py_clob_client",
    "py_clob_client.client",
    "py_clob_client.clob_types",
    "trading.config",
    "shared.db",
    "colorama",
]:
    sys.modules[mod] = MagicMock()


passed = 0
failed = 0


def check(num, name, condition):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {num}. {name}")
    if condition:
        passed += 1
    else:
        failed += 1


print("=== S03 Verification: Trading Adapter Pipeline ===\n")

# ── Import checks (1-3) ────────────────────────────────────────────

print("Import checks")

try:
    from trading.strategy_adapter import evaluate_strategies, ticks_to_snapshot
    check(1, "Import evaluate_strategies, ticks_to_snapshot from adapter", True)
except ImportError as e:
    check(1, f"Import adapter functions — {e}", False)
    print("  FATAL: cannot proceed without adapter imports")
    sys.exit(1)

try:
    from shared.strategies import MarketSnapshot, Signal, get_strategy
    check(2, "Import MarketSnapshot, Signal, get_strategy from shared.strategies", True)
except ImportError as e:
    check(2, f"Import shared strategies — {e}", False)

import inspect
check(3, "evaluate_strategies is a coroutine function",
      inspect.iscoroutinefunction(evaluate_strategies))

# ── Tick-to-snapshot conversion checks (4-7) ───────────────────────

print("\nTick-to-snapshot conversion checks")
import numpy as np
from datetime import datetime, timezone, timedelta
from trading.db import MarketInfo, Tick

# Build synthetic market: 5-minute duration = 300 seconds
market_start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
market_end = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

mock_market = MarketInfo(
    market_id="test-market-s03",
    market_type="BTC_5m",
    started_at=market_start,
    ended_at=market_end,
)

# Create ticks at known seconds with gaps
# Ticks at seconds: 0, 1, 2, 10, 50, 100.  Gap at seconds 3-9, 11-49, etc.
tick_data = [
    (0, 0.50),
    (1, 0.52),
    (2, 0.54),
    (10, 0.60),
    (50, 0.55),
    (100, 0.48),
]
ticks = [
    Tick(
        market_id="test-market-s03",
        time=market_start + timedelta(seconds=s),
        up_price=price,
        down_price=round(1.0 - price, 6),
    )
    for s, price in tick_data
]

snapshot = ticks_to_snapshot(mock_market, ticks)

# Check 4: returns MarketSnapshot
check(4, "ticks_to_snapshot returns MarketSnapshot", isinstance(snapshot, MarketSnapshot))

# Check 5: prices shape is (300,) for 5-minute market
check(5, "snapshot.prices shape is (300,)", snapshot.prices.shape == (300,))

# Check 6: NaN present for gap seconds (e.g. second 5 has no tick)
check(6, "NaN at gap seconds (second 5 has no tick)", np.isnan(snapshot.prices[5]))

# Check 7: Known tick prices at correct indices
prices_ok = (
    snapshot.prices[0] == 0.50
    and snapshot.prices[1] == 0.52
    and snapshot.prices[10] == 0.60
    and snapshot.prices[100] == 0.48
)
check(7, "Known tick prices at correct indices (s=0→0.50, s=10→0.60, s=100→0.48)", prices_ok)

# ── Strategy evaluation + signal field checks (8-14) ───────────────

print("\nStrategy evaluation + signal field checks")

# Build spike-reversion synthetic data calibrated per KNOWLEDGE.md:
# Spike peak early (s=4-5), sharp reversion, entry_price ≤ 0.35
# Thresholds: spike_threshold_up=0.80, reversion_reversal_pct=0.10,
#             min_reversion_ticks=10, entry_price_threshold=0.35

spike_prices = np.full(300, np.nan)

# Ramp to 0.85 by s=4 (detection window spike)
spike_prices[0:5] = [0.50, 0.60, 0.70, 0.80, 0.85]
# Hold spike briefly
spike_prices[5:8] = 0.85
# Sharp reversion: 0.85 → 0.75 over 4 seconds
# (0.85 - 0.75)/0.85 ≈ 0.118 ≥ 0.10 threshold ✓
# entry_price = 1.0 - 0.75 = 0.25 ≤ 0.35 ✓
spike_prices[8:12] = [0.82, 0.79, 0.76, 0.75]
# Fill rest with stable post-reversion prices
spike_prices[12:] = 0.70

spike_snapshot = MarketSnapshot(
    market_id="test-spike-s03",
    market_type="BTC_5m",
    prices=spike_prices,
    total_seconds=300,
    elapsed_seconds=300,  # full data (as if post-market / all ticks available)
    metadata={"started_at": market_start},
)

# Check 8: S1 strategy returns Signal on spike data
strategy = get_strategy("S1")
signal = strategy.evaluate(spike_snapshot)
check(8, "get_strategy('S1').evaluate(spike_snapshot) returns Signal (not None)",
      signal is not None and isinstance(signal, Signal))

if signal:
    # Check 9: Direction is Down (contrarian to up-spike)
    check(9, "Signal direction is 'Down' (contrarian to up-spike)",
          signal.direction == "Down")

    # Check 10: signal_data has reversion_second key
    check(10, "Signal.signal_data has 'reversion_second' key",
          "reversion_second" in signal.signal_data)
else:
    check(9, "Signal direction (skipped — no signal)", False)
    check(10, "reversion_second (skipped — no signal)", False)

# Checks 11-14: Test _populate_execution_fields with a synthetic signal
from trading.strategy_adapter import _populate_execution_fields

# Create a signal like evaluate() would return
test_signal = Signal(
    direction="Down",
    strategy_name="S1_spike_reversion",
    entry_price=0.25,
    signal_data={
        "spike_direction": "Up",
        "reversion_second": 11,
        "spike_peak": 0.85,
    },
)

test_balance = 200.0  # $200 balance

populated = _populate_execution_fields(test_signal, mock_market, spike_snapshot, test_balance)

if populated is not None:
    # Check 11: locked_shares > 0
    check(11, f"locked_shares > 0 (got {populated.locked_shares})",
          populated.locked_shares > 0)

    # Check 12: locked_cost > 0
    check(12, f"locked_cost > 0 (got {populated.locked_cost})",
          populated.locked_cost > 0)

    # Check 13: signal_data has price_min and price_max
    has_price_bounds = (
        "price_min" in populated.signal_data
        and "price_max" in populated.signal_data
    )
    check(13, "signal_data has 'price_min' and 'price_max'", has_price_bounds)

    # Check 14: profitability_thesis is a non-empty string
    thesis = populated.signal_data.get("profitability_thesis", "")
    check(14, f"profitability_thesis is non-empty string (len={len(thesis)})",
          isinstance(thesis, str) and len(thesis) > 0)
else:
    check(11, "locked_shares (skipped — populate returned None)", False)
    check(12, "locked_cost (skipped — populate returned None)", False)
    check(13, "price_min/price_max (skipped — populate returned None)", False)
    check(14, "profitability_thesis (skipped — populate returned None)", False)

# ── Guard + edge case checks (15) ──────────────────────────────────

print("\nGuard + edge case checks")

# Check 15: Empty tick list produces all-NaN array without crashing
empty_snapshot = ticks_to_snapshot(mock_market, [])
all_nan = np.all(np.isnan(empty_snapshot.prices))
check(15, "ticks_to_snapshot with empty ticks → all-NaN array (no crash)", all_nan)

# ── Integrity + isolation checks (16-18) ────────────────────────────

print("\nIntegrity + isolation checks")

import hashlib
import pathlib

def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

# Check 16: executor.py hash matches original
worktree_root = pathlib.Path(__file__).resolve().parent.parent  # src/
original_root = pathlib.Path("/Users/igol/Documents/repo/polyedge/src")

executor_wt = file_sha256(worktree_root / "trading" / "executor.py")
executor_orig = file_sha256(original_root / "trading" / "executor.py")
check(16, "executor.py hash matches original (R009 — unmodified)",
      executor_wt == executor_orig)

# Check 17: redeemer.py and balance.py hashes match originals
redeemer_wt = file_sha256(worktree_root / "trading" / "redeemer.py")
redeemer_orig = file_sha256(original_root / "trading" / "redeemer.py")
balance_wt = file_sha256(worktree_root / "trading" / "balance.py")
balance_orig = file_sha256(original_root / "trading" / "balance.py")
both_match = (redeemer_wt == redeemer_orig and balance_wt == balance_orig)
check(17, "redeemer.py + balance.py hashes match originals (R009 — unmodified)", both_match)

# Check 18: No analysis.* or core.* imports in strategy_adapter.py (AST isolation)
import ast

adapter_path = worktree_root / "trading" / "strategy_adapter.py"
adapter_source = adapter_path.read_text()
tree = ast.parse(adapter_source)
forbidden = []
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        module = getattr(node, "module", "") or ""
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [module]
        for name in names:
            if name and any(name.startswith(p) for p in ("analysis", "core")):
                forbidden.append(name)
check(18, f"No analysis.*/core.* imports in strategy_adapter.py (found: {forbidden})",
      len(forbidden) == 0)

# ── Summary ─────────────────────────────────────────────────────────

print(f"\n=== S03 Results: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
