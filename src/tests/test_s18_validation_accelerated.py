from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.accelerators import get_strategy_kernel
from analysis.validation import StrategyCandidate, run_validation_suite
from shared.strategies.S18 import config as s18_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S18").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _market(base_started_at, market_id: str, with_features: bool) -> dict:
    prices = np.array([0.52] * 31 + [0.54, 0.56, 0.58, 0.60, 0.62, 0.65, 0.68], dtype=float)
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
            "underlying_return_5s": np.array([np.nan] * 31 + [0.002] * 7, dtype=float),
            "underlying_return_10s": np.array([np.nan] * 31 + [0.002] * 7, dtype=float),
            "underlying_return_30s": np.array([np.nan] * 31 + [0.002] * 7, dtype=float),
            "underlying_realized_vol_30s": np.array([np.nan] * 31 + [0.005] * 7, dtype=float),
            "underlying_trade_count": np.array([np.nan] * 31 + [80.0] * 7, dtype=float),
            "market_up_delta_5s": np.array([np.nan] * 31 + [0.001] * 7, dtype=float),
        }
    return market


def test_s18_accelerated_validation_reports_feature_eligibility(monkeypatch, base_started_at):
    monkeypatch.setattr(s18_config, "get_param_grid", lambda: {
        "entry_window_start": [31],
        "entry_window_end": [37],
        "min_return_30s": [0.001],
        "min_return_10s": [0.001],
        "min_return_5s": [0.001],
        "acceleration_ratio": [0.5],
        "max_underlying_vol": [0.02],
        "min_trade_count": [40.0],
        "max_price_distance_from_mid": [0.20],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })

    candidate = StrategyCandidate(
        strategy_id="S18",
        param_dict={
            "entry_window_start": 31,
            "entry_window_end": 37,
            "min_return_30s": 0.001,
            "min_return_10s": 0.001,
            "min_return_5s": 0.001,
            "acceleration_ratio": 0.5,
            "max_underlying_vol": 0.02,
            "min_trade_count": 40.0,
            "max_price_distance_from_mid": 0.20,
            "stop_loss": 0.20,
            "take_profit": 0.80,
        },
    )

    results = run_validation_suite(
        candidate,
        [
            _market(base_started_at, "s18_with_features", with_features=True),
            _market(base_started_at, "s18_missing_features", with_features=False),
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
