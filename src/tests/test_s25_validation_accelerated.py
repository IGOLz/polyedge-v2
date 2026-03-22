from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.accelerators import get_strategy_kernel
from analysis.validation import StrategyCandidate, run_validation_suite
from shared.strategies.S25 import config as s25_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S25").is_available(),
    reason="Numba-backed accelerators are not available in this environment.",
)


@pytest.fixture
def base_started_at():
    return datetime(2026, 3, 10, tzinfo=timezone.utc)


def _market(base_started_at, market_id: str, with_features: bool) -> dict:
    total_seconds = 100
    prices = np.full(total_seconds, 0.50, dtype=float)
    prices[39:] = 0.74
    market = {
        "market_id": market_id,
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": total_seconds,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "final_outcome": "Up",
        "prices": prices,
        "feature_series": {},
    }
    if with_features:
        active = np.arange(total_seconds) >= 39
        market["feature_series"] = {
            "underlying_return_5s": np.where(active, 0.0012, np.nan),
            "market_up_delta_5s": np.where(active, 0.004, np.nan),
            "underlying_trade_count": np.where(active, 20.0, np.nan),
        }
    return market


def test_s25_accelerated_validation_reports_feature_eligibility(monkeypatch, base_started_at):
    monkeypatch.setattr(s25_config, "get_param_grid", lambda: {
        "checkpoint_tolerance": [2],
        "min_underlying_return_5s": [0.0006],
        "underlying_beta": [12.0],
        "min_directional_gap": [0.008],
        "min_market_delta_5s": [0.002],
        "min_trade_count": [15.0],
        "min_price_distance_from_mid": [0.05],
        "max_entry_price": [0.80],
        "stop_loss": [0.20],
        "take_profit": [0.80],
    })

    candidate = StrategyCandidate(
        strategy_id="S25",
        param_dict={
            "checkpoint_tolerance": 2,
            "min_underlying_return_5s": 0.0006,
            "underlying_beta": 12.0,
            "min_directional_gap": 0.008,
            "min_market_delta_5s": 0.002,
            "min_trade_count": 15.0,
            "min_price_distance_from_mid": 0.05,
            "max_entry_price": 0.80,
            "stop_loss": 0.20,
            "take_profit": 0.80,
        },
    )

    results = run_validation_suite(
        candidate,
        [
            _market(base_started_at, "s25_with_features", with_features=True),
            _market(base_started_at, "s25_missing_features", with_features=False),
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
