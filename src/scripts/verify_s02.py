"""S02 verification — analysis adapter pipeline (no DB required).

Run from src/ directory:
    cd src && PYTHONPATH=. python3 scripts/verify_s02.py
"""
import sys

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


print("=== S02 Verification: Analysis Adapter Pipeline ===\n")

# ── Import checks ───────────────────────────────────────────────────

print("Import checks")
try:
    from analysis.backtest_strategies import market_to_snapshot, run_strategy, main
    check(1, "Import market_to_snapshot, run_strategy, main from adapter", True)
except ImportError as e:
    check(1, f"Import adapter functions — {e}", False)

try:
    from shared.strategies import MarketSnapshot, Signal, get_strategy
    check(2, "Import MarketSnapshot, Signal, get_strategy from shared.strategies", True)
except ImportError as e:
    check(2, f"Import shared strategies — {e}", False)

try:
    from analysis.backtest.engine import make_trade, compute_metrics, Trade
    check(3, "Import make_trade, compute_metrics, Trade from engine", True)
except ImportError as e:
    check(3, f"Import engine — {e}", False)

# ── Synthetic market data ───────────────────────────────────────────

print("\nConversion checks")
import numpy as np
from datetime import datetime, timezone

prices = np.full(300, np.nan)  # 5-minute market = 300 seconds
# Up-spike: price jumps to 0.85 in first 5 seconds of detection window
prices[0:5] = [0.50, 0.60, 0.70, 0.80, 0.85]
# Hold spike briefly
prices[5:8] = 0.85
# Sharp reversion: drop from 0.85 to 0.75 over 4 seconds
# Peak at s=4, scan window: s=5..s=14 (min_reversion_ticks=10)
# At 0.75: reversion = (0.85 - 0.75) / 0.85 ≈ 0.118 ≥ 0.10 ✓
# entry_price = 1.0 - 0.75 = 0.25 ≤ 0.35 ✓
prices[8:12] = [0.82, 0.79, 0.76, 0.75]
# Fill rest with stable post-reversion prices
for s in range(12, 300):
    prices[s] = 0.70

synthetic_market = {
    "market_id": "test-market-001",
    "market_type": "BTC_5m",
    "asset": "BTC",
    "duration_minutes": 5,
    "total_seconds": 300,
    "started_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    "ended_at": datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
    "final_outcome": "Down",
    "hour": 12,
    "ticks": prices,
}

# Check 4: market_to_snapshot returns MarketSnapshot
snapshot = market_to_snapshot(synthetic_market)
check(4, "market_to_snapshot returns MarketSnapshot", isinstance(snapshot, MarketSnapshot))

# Check 5: prices shape
check(5, "snapshot.prices shape is (300,)", snapshot.prices.shape == (300,))

# Check 6: elapsed_seconds equals total_seconds (backtest convention)
check(6, "snapshot.elapsed_seconds == 300", snapshot.elapsed_seconds == 300)

# Check 7: metadata fields present and correct
meta_ok = (
    snapshot.metadata.get("asset") == "BTC"
    and "hour" in snapshot.metadata
    and "started_at" in snapshot.metadata
    and "final_outcome" in snapshot.metadata
    and "duration_minutes" in snapshot.metadata
)
check(7, "snapshot.metadata has asset/hour/started_at/final_outcome/duration_minutes", meta_ok)

# ── Strategy evaluation checks ──────────────────────────────────────

print("\nStrategy evaluation checks")

strategy = get_strategy("S1")
check(8, "get_strategy('S1') returns a strategy instance", strategy is not None)

signal = strategy.evaluate(snapshot)
check(9, "strategy.evaluate(snapshot) returns Signal (not None)", signal is not None and isinstance(signal, Signal))

if signal:
    check(10, "Signal direction is 'Down' (contrarian to up-spike)", signal.direction == "Down")
    rev_sec = signal.signal_data.get("reversion_second")
    check(11, f"signal_data['reversion_second'] is int > 0 (got {rev_sec})",
          isinstance(rev_sec, (int, np.integer)) and rev_sec > 0)
else:
    check(10, "Signal direction (skipped — no signal)", False)
    check(11, "reversion_second (skipped — no signal)", False)

# ── Trade pipeline checks ──────────────────────────────────────────

print("\nTrade pipeline checks")

if signal:
    second_entered = int(signal.signal_data["reversion_second"])
    trade = make_trade(synthetic_market, second_entered, signal.entry_price, signal.direction)
    check(12, "make_trade returns a Trade object", isinstance(trade, Trade))

    check(13, "Trade.direction matches Signal.direction",
          trade.direction == signal.direction)

    metrics = compute_metrics([trade], config_id="S1")
    required_keys = {"total_bets", "win_rate_pct", "total_pnl", "config_id"}
    check(14, "compute_metrics returns dict with total_bets/win_rate_pct/total_pnl",
          isinstance(metrics, dict) and required_keys.issubset(metrics.keys()))

    check(15, "metrics['total_bets'] == 1", metrics.get("total_bets") == 1)
else:
    check(12, "make_trade (skipped — no signal)", False)
    check(13, "Trade direction (skipped — no signal)", False)
    check(14, "compute_metrics (skipped — no signal)", False)
    check(15, "total_bets == 1 (skipped — no signal)", False)

# ── Integration checks ─────────────────────────────────────────────

print("\nIntegration checks")

trades_list, metrics_dict = run_strategy("S1", strategy, [synthetic_market])
check(16, "run_strategy returns (trades, metrics) tuple",
      isinstance(trades_list, list) and isinstance(metrics_dict, dict))

check(17, "run_strategy produces >= 1 trade", len(trades_list) >= 1)

# Module isolation: no trading.* or core.* imports in the adapter
import ast
import pathlib

adapter_path = pathlib.Path(__file__).resolve().parent.parent / "analysis" / "backtest_strategies.py"
adapter_source = adapter_path.read_text()
tree = ast.parse(adapter_source)
forbidden = []
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        module = getattr(node, "module", "") or ""
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [module]
        for name in names:
            if name and any(name.startswith(p) for p in ("trading", "core")):
                forbidden.append(name)
check(18, f"No trading.*/core.* imports in adapter (found: {forbidden})", len(forbidden) == 0)

# ── Summary ─────────────────────────────────────────────────────────

print(f"\n=== S02 Results: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
