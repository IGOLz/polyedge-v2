from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from analysis.accelerators import get_strategy_kernel
from analysis.validation import StrategyCandidate, run_validation_suite
from shared.strategies.S14 import config as s14_config


pytestmark = pytest.mark.skipif(
    not get_strategy_kernel("S14").is_available(),
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
        "total_seconds": 50,
        "started_at": base_started_at,
        "ended_at": base_started_at,
        "hour": 12,
        "final_outcome": "Up",
        "prices": np.array([0.50] * 45 + [0.34, 0.40, 0.76, 0.76, 0.76], dtype=float),
        "feature_series": {},
    }
    if with_features:
        market["feature_series"] = {
            "underlying_return_30s": np.array([np.nan] * 45 + [0.0005] * 5, dtype=float),
            "market_up_delta_30s": np.array([np.nan] * 45 + [-0.06] * 5, dtype=float),
            "direction_mismatch_30s": np.array([np.nan] * 45 + [1.0] * 5, dtype=float),
        }
    return market


def test_s14_accelerated_validation_reports_feature_eligibility(monkeypatch, base_started_at):
    monkeypatch.setattr(s14_config, "get_param_grid", lambda: {
        "feature_window": [30],
        "entry_window_start": [45],
        "entry_window_end": [49],
        "min_market_delta_abs": [0.06],
        "max_underlying_return_abs": [0.0015],
        "extreme_price_low": [0.35],
        "extreme_price_high": [0.65],
        "require_direction_mismatch": [True],
        "stop_loss": [0.25],
        "take_profit": [0.75],
    })

    candidate = StrategyCandidate(
        strategy_id="S14",
        param_dict={
            "feature_window": 30,
            "entry_window_start": 45,
            "entry_window_end": 49,
            "min_market_delta_abs": 0.06,
            "max_underlying_return_abs": 0.0015,
            "extreme_price_low": 0.35,
            "extreme_price_high": 0.65,
            "require_direction_mismatch": True,
            "stop_loss": 0.25,
            "take_profit": 0.75,
        },
    )

    results = run_validation_suite(
        candidate,
        [
            _market(base_started_at, "s14_with_features", with_features=True),
            _market(base_started_at, "s14_missing_features", with_features=False),
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
