from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.accelerators import get_strategy_kernel
from analysis.validation import StrategyCandidate, run_validation_suite
from shared.strategies.S13 import config as s13_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S13").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _market(base_started_at, market_id: str, with_features: bool) -> dict:
    market = {
        "market_id": market_id,
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": 8,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "final_outcome": "Up",
        "prices": np.array([0.48, 0.52, 0.54, 0.57, 0.60, 0.63, 0.66, 0.70], dtype=float),
        "feature_series": {},
    }
    if with_features:
        market["feature_series"] = {
            "underlying_return_5s": np.array([np.nan, 0.002, 0.002, 0.003, 0.003, 0.004, 0.004, 0.004], dtype=float),
            "market_up_delta_5s": np.array([np.nan, 0.003, 0.004, 0.005, 0.006, 0.006, 0.006, 0.006], dtype=float),
            "underlying_realized_vol_10s": np.array([0.005] * 8, dtype=float),
        }
    return market


def test_s13_accelerated_validation_reports_feature_eligibility(monkeypatch, base_started_at):
    monkeypatch.setattr(s13_config, "get_param_grid", lambda: {
        "feature_window": [5],
        "entry_window_start": [1],
        "entry_window_end": [6],
        "min_underlying_return": [0.001],
        "min_market_confirmation": [0.0],
        "max_market_delta": [0.05],
        "max_price_distance_from_mid": [0.20],
        "max_underlying_vol": [0.02],
        "stop_loss": [0.25],
        "take_profit": [0.80],
    })

    candidate = StrategyCandidate(
        strategy_id="S13",
        param_dict={
            "feature_window": 5,
            "entry_window_start": 1,
            "entry_window_end": 6,
            "min_underlying_return": 0.001,
            "min_market_confirmation": 0.0,
            "max_market_delta": 0.05,
            "max_price_distance_from_mid": 0.20,
            "max_underlying_vol": 0.02,
            "stop_loss": 0.25,
            "take_profit": 0.80,
        },
    )

    results = run_validation_suite(
        candidate,
        [
            _market(base_started_at, "s13_with_features", with_features=True),
            _market(base_started_at, "s13_missing_features", with_features=False),
        ],
        base_slippage=0.0,
        chronological_folds=2,
        bootstrap_iterations=10,
        include_neighbors=False,
    )

    assert results["dataset"]["total_markets"] == 2
    assert results["dataset"]["eligible_markets"] == 1
    assert results["overall"]["metrics"]["eligible_markets"] == 1
    assert results["overall"]["metrics"]["skipped_markets_missing_features"] == 1
