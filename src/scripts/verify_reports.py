#!/usr/bin/env python3
"""Verify M002: Unified Strategy Reports.

Tests the shared report model (StrategyReport) and verifies that both
the backtest adapter and trading report module produce reports in the
same format with the same field set.

Run: cd src && PYTHONPATH=. python3 scripts/verify_reports.py
"""

import json
import os
import sys
import tempfile

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


print("=== M002 Verification: Unified Strategy Reports ===\n")

# ── 1. Import checks ───────────────────────────────────────────────
print("1. Import checks")

try:
    from shared.strategies.report import StrategyReport
    check("StrategyReport importable", True)
except Exception as e:
    check("StrategyReport importable", False, str(e))
    sys.exit(1)

try:
    from shared.strategies import StrategyReport as SR
    check("StrategyReport re-exported from shared.strategies", SR is StrategyReport)
except Exception as e:
    check("StrategyReport re-exported from shared.strategies", False, str(e))

# ── 2. Report construction ─────────────────────────────────────────
print("\n2. Report construction from metrics")

# Simulate engine.compute_metrics output
mock_metrics = {
    "config_id": "S1",
    "total_bets": 50,
    "wins": 30,
    "losses": 20,
    "win_rate_pct": 60.0,
    "total_pnl": 12.5,
    "avg_bet_pnl": 0.25,
    "profit_factor": 1.8,
    "expected_value": 0.15,
    "sharpe_ratio": 0.85,
    "sortino_ratio": 1.2,
    "max_drawdown": 3.5,
    "std_dev_pnl": 0.3,
    "pct_profitable_assets": 75.0,
    "pct_profitable_durations": 100.0,
    "consistency_score": 72.5,
    "q1_pnl": 4.0,
    "q2_pnl": 3.0,
    "q3_pnl": 2.5,
    "q4_pnl": 3.0,
}

report = StrategyReport.from_metrics(
    mock_metrics,
    strategy_id="S1",
    strategy_name="S1_spike_reversion",
    context="backtest",
    total_markets=1000,
    date_range_start="2026-01-01",
    date_range_end="2026-03-18",
    config={"spike_threshold_up": 0.80, "reversion_reversal_pct": 0.10},
    ranking_score=75.0,
)

check("strategy_id = S1", report.strategy_id == "S1")
check("context = backtest", report.context == "backtest")
check("total_bets = 50", report.total_bets == 50)
check("win_rate_pct = 60.0", report.win_rate_pct == 60.0)
check("total_pnl = 12.5", report.total_pnl == 12.5)
check("sharpe_ratio = 0.85", report.sharpe_ratio == 0.85)
check("ranking_score = 75.0", report.ranking_score == 75.0)
check("config preserved", report.config.get("spike_threshold_up") == 0.80)

# ── 3. JSON round-trip ─────────────────────────────────────────────
print("\n3. JSON serialization round-trip")

with tempfile.TemporaryDirectory() as tmpdir:
    json_path = os.path.join(tmpdir, "S1.json")
    report.to_json(json_path)

    check("JSON file created", os.path.exists(json_path))

    with open(json_path) as f:
        data = json.load(f)

    check("JSON has strategy_id", data.get("strategy_id") == "S1")
    check("JSON has context", data.get("context") == "backtest")
    check("JSON has total_bets", data.get("total_bets") == 50)
    check("JSON has sharpe_ratio", data.get("sharpe_ratio") == 0.85)
    check("JSON has config", data.get("config", {}).get("spike_threshold_up") == 0.80)
    check("JSON has generated_at", "generated_at" in data and len(data["generated_at"]) > 0)

    # Load back
    loaded = StrategyReport.from_json(json_path)
    check("Loaded strategy_id matches", loaded.strategy_id == report.strategy_id)
    check("Loaded total_pnl matches", loaded.total_pnl == report.total_pnl)
    check("Loaded context matches", loaded.context == report.context)

# ── 4. Markdown generation ─────────────────────────────────────────
print("\n4. Markdown generation")

with tempfile.TemporaryDirectory() as tmpdir:
    md_path = os.path.join(tmpdir, "S1.md")
    report.to_markdown(md_path)

    check("Markdown file created", os.path.exists(md_path))

    with open(md_path) as f:
        content = f.read()

    check("Markdown has title", "S1: S1_spike_reversion" in content)
    check("Markdown has context", "Backtest" in content)
    check("Markdown has win rate", "60.00%" in content)
    check("Markdown has PnL", "12.5" in content)
    check("Markdown has Sharpe", "0.85" in content)
    check("Markdown has config block", "spike_threshold_up" in content)

# ── 5. Live context report ─────────────────────────────────────────
print("\n5. Live context report (same structure)")

live_report = StrategyReport.from_metrics(
    mock_metrics,
    strategy_id="S1",
    strategy_name="S1_spike_reversion",
    context="live",
    ranking_score=68.0,
)

check("Live report context = live", live_report.context == "live")
check("Live report same total_bets", live_report.total_bets == 50)
check("Live report same sharpe", live_report.sharpe_ratio == 0.85)

# Compare field sets
backtest_fields = set(report.to_dict().keys())
live_fields = set(live_report.to_dict().keys())
check("Backtest and live have identical field sets", backtest_fields == live_fields,
      f"diff: {backtest_fields.symmetric_difference(live_fields)}" if backtest_fields != live_fields else "")

# ── 6. Trade records ───────────────────────────────────────────────
print("\n6. Trade records in report")

# Simulate a Trade dataclass object
class FakeTrade:
    market_id = "abc123"
    direction = "Down"
    entry_price = 0.65
    exit_price = 1.0
    outcome = "win"
    pnl = 0.35
    second_entered = 12
    asset = "BTC"
    duration_minutes = 5

report_with_trades = StrategyReport.from_metrics(
    mock_metrics,
    [FakeTrade()],
    strategy_id="S1",
    strategy_name="S1_spike_reversion",
    context="backtest",
)

check("Trade records populated", len(report_with_trades.trades) == 1)
check("Trade has market_id", report_with_trades.trades[0].get("market_id") == "abc123")
check("Trade has pnl", report_with_trades.trades[0].get("pnl") == 0.35)

# ── 7. Analysis adapter generates reports ──────────────────────────
print("\n7. Analysis adapter import check")

try:
    from analysis.backtest_strategies import _generate_reports
    check("_generate_reports importable from backtest adapter", True)
except Exception as e:
    check("_generate_reports importable from backtest adapter", False, str(e))

# ── 8. Trading report module ──────────────────────────────────────
print("\n8. Trading report module import check")

# Mock py_clob_client before importing trading modules
from unittest.mock import MagicMock
for mod_name in ['py_clob_client', 'py_clob_client.client', 'py_clob_client.clob_types',
                 'py_clob_client.order_builder', 'py_clob_client.order_builder.constants']:
    sys.modules.setdefault(mod_name, MagicMock())

try:
    from trading.report import compute_live_metrics, generate_live_reports
    check("compute_live_metrics importable", True)
    check("generate_live_reports importable", True)
except Exception as e:
    check("Trading report imports", False, str(e))

# ── 9. compute_live_metrics produces same field set ────────────────
print("\n9. Live metrics field parity with engine.compute_metrics")

from trading.report import compute_live_metrics

live_trades = [
    {"pnl": 0.35, "outcome": "win", "asset": "BTC", "duration_minutes": 5},
    {"pnl": -0.25, "outcome": "loss", "asset": "BTC", "duration_minutes": 5},
    {"pnl": 0.40, "outcome": "win", "asset": "ETH", "duration_minutes": 5},
    {"pnl": -0.30, "outcome": "loss", "asset": "ETH", "duration_minutes": 5},
    {"pnl": 0.50, "outcome": "win", "asset": "BTC", "duration_minutes": 15},
]
live_metrics = compute_live_metrics(live_trades, "S1_spike_reversion")

# Expected field set from engine.compute_metrics
expected_fields = {
    "config_id", "total_bets", "wins", "losses", "win_rate_pct",
    "total_pnl", "avg_bet_pnl", "profit_factor", "expected_value",
    "sharpe_ratio", "sortino_ratio", "max_drawdown", "std_dev_pnl",
    "pct_profitable_assets", "pct_profitable_durations", "consistency_score",
    "q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl",
}
actual_fields = set(live_metrics.keys())
check("Live metrics has all engine fields", expected_fields.issubset(actual_fields),
      f"missing: {expected_fields - actual_fields}" if not expected_fields.issubset(actual_fields) else "")
check("Live metrics total_bets = 5", live_metrics["total_bets"] == 5)
check("Live metrics wins = 3", live_metrics["wins"] == 3)
check("Live metrics losses = 2", live_metrics["losses"] == 2)
check("Live metrics total_pnl > 0", live_metrics["total_pnl"] > 0)
check("Live metrics win_rate_pct = 60.0", live_metrics["win_rate_pct"] == 60.0)

# ── 10. Empty trades handling ──────────────────────────────────────
print("\n10. Edge cases")

empty_metrics = compute_live_metrics([], "S1")
check("Empty trades → total_bets = 0", empty_metrics["total_bets"] == 0)
check("Empty trades → total_pnl = 0", empty_metrics["total_pnl"] == 0)

# Single trade
single_metrics = compute_live_metrics(
    [{"pnl": 0.50, "outcome": "win", "asset": "BTC", "duration_minutes": 5}],
    "S1",
)
check("Single trade → total_bets = 1", single_metrics["total_bets"] == 1)
check("Single trade → wins = 1", single_metrics["wins"] == 1)

# ── Summary ─────────────────────────────────────────────────────────
print(f"\n=== Results: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
