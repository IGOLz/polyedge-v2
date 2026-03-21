from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.accelerators import get_strategy_kernel
from analysis.validation import StrategyCandidate, run_validation_suite
from shared.strategies.S15 import config as s15_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S15").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _market(base_started_at, market_id: str, with_features: bool) -> dict:
    prices = np.array([0.40] * 31 + [0.42, 0.42, 0.42, 0.42, 0.50, 0.76, 0.76], dtype=float)
    market = {
        "market_id": market_id,
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": len(prices),
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "final_outcome": "Up",
        "prices": prices,
        "feature_series": {},
    }
    if with_features:
        market["feature_series"] = {
            "underlying_return_5s": np.array([np.nan] * 31 + [0.001] * 7, dtype=float),
            "underlying_trade_count": np.array([np.nan] * 31 + [80.0] * 7, dtype=float),
        }
    return market


def test_s15_accelerated_validation_reports_feature_eligibility(monkeypatch, base_started_at):
    monkeypatch.setattr(s15_config, "get_param_grid", lambda: {
        "setup_window_end": [30],
        "breakout_scan_start": [31],
        "breakout_scan_end": [37],
        "breakout_buffer": [0.01],
        "confirmation_points": [1],
        "feature_window": [5],
        "min_underlying_return": [0.0005],
        "min_trade_count": [40.0],
        "stop_loss": [0.35],
        "take_profit": [0.75],
    })

    candidate = StrategyCandidate(
        strategy_id="S15",
        param_dict={
            "setup_window_end": 30,
            "breakout_scan_start": 31,
            "breakout_scan_end": 37,
            "breakout_buffer": 0.01,
            "confirmation_points": 1,
            "feature_window": 5,
            "min_underlying_return": 0.0005,
            "min_trade_count": 40.0,
            "stop_loss": 0.35,
            "take_profit": 0.75,
        },
    )

    results = run_validation_suite(
        candidate,
        [
            _market(base_started_at, "s15_with_features", with_features=True),
            _market(base_started_at, "s15_missing_features", with_features=False),
        ],
        base_slippage=0.0,
        chronological_folds=2,
        bootstrap_iterations=10,
        include_neighbors=False,
    )

    assert results["dataset"]["total_markets"] == 2
    assert results["dataset"]["eligible_markets"] == 1
    assert results["overall"]["accelerated"] is True
    assert results["overall"]["metrics"]["eligible_markets"] == 1
    assert results["overall"]["metrics"]["skipped_markets_missing_features"] == 1
    assert len(results["chronological_folds"]) == 1
    assert len(results["asset_slices"]) == 1
    assert len(results["duration_slices"]) == 1
    assert len(results["day_slices"]) == 1
