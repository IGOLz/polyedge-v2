from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analysis.validation import (
    StrategyCandidate,
    candidate_from_results_csv,
    compare_candidate_to_defaults,
    render_validation_markdown,
    run_validation_suite,
)


def _make_market(
    market_id: str,
    *,
    asset: str,
    started_at: datetime,
    final_outcome: str,
    prices: np.ndarray,
    duration_minutes: int = 5,
) -> dict:
    return {
        "market_id": market_id,
        "market_type": f"{asset}_{duration_minutes}m",
        "asset": asset,
        "duration_minutes": duration_minutes,
        "total_seconds": len(prices),
        "started_at": started_at,
        "ended_at": started_at + timedelta(seconds=len(prices)),
        "final_outcome": final_outcome,
        "hour": started_at.hour,
        "prices": prices,
        "feature_series": {},
    }


def _synthetic_s3_markets() -> list[dict]:
    base = datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc)

    down_prices = np.full(90, 0.55, dtype=float)
    down_prices[30:37] = [0.78, 0.85, 0.83, 0.79, 0.74, 0.68, 0.62]
    down_prices[37:] = 0.30

    up_prices = np.full(90, 0.45, dtype=float)
    up_prices[20:27] = [0.22, 0.15, 0.18, 0.22, 0.27, 0.33, 0.36]
    up_prices[27:] = 0.72

    flat_prices = np.full(90, 0.50, dtype=float)

    return [
        _make_market(
            "s3_down_market",
            asset="btc",
            started_at=base,
            final_outcome="Down",
            prices=down_prices,
            duration_minutes=5,
        ),
        _make_market(
            "s3_up_market",
            asset="eth",
            started_at=base + timedelta(days=1),
            final_outcome="Up",
            prices=up_prices,
            duration_minutes=15,
        ),
        _make_market(
            "s3_flat_market",
            asset="sol",
            started_at=base + timedelta(days=2),
            final_outcome="Up",
            prices=flat_prices,
            duration_minutes=5,
        ),
    ]


def test_candidate_from_results_csv_coerces_grid_values(tmp_path):
    csv_path = tmp_path / "s5_results.csv"
    pd.DataFrame(
        [
            {
                "config_id": "S5_test",
                "entry_window_start": 45,
                "entry_window_end": 240,
                "allowed_hours": "[18, 19, 20, 21, 22, 23]",
                "price_range_low": 0.45,
                "price_range_high": 0.6,
                "approach_lookback": 12,
                "cross_buffer": 0.015,
                "confirmation_lookback": 5,
                "confirmation_min_move": 0.01,
                "min_cross_move": 0.04,
                "stop_loss": 0.35,
                "take_profit": 0.7,
                "total_bets": 100,
                "total_pnl": 5.0,
            }
        ]
    ).to_csv(csv_path, index=False)

    candidate = candidate_from_results_csv("S5", csv_path, rank=1)

    assert candidate.config_id == "S5_test"
    assert candidate.param_dict["allowed_hours"] == [18, 19, 20, 21, 22, 23]
    assert candidate.param_dict["entry_window_end"] == 240
    assert candidate.param_dict["cross_buffer"] == 0.015


def test_compare_candidate_to_defaults_flags_live_exit_drift():
    candidate = StrategyCandidate(
        strategy_id="S3",
        param_dict={
            "spike_threshold": 0.78,
            "spike_lookback": 30,
            "reversion_pct": 0.18,
            "min_reversion_sec": 45,
            "entry_window_start": 5,
            "entry_window_end": 120,
            "min_seconds_since_extremum": 2,
            "min_distance_from_mid": 0.08,
            "stop_loss": 0.20,
            "take_profit": 0.85,
        },
    )

    drift = compare_candidate_to_defaults(candidate)
    drift_fields = {row["field"] for row in drift}

    assert "spike_lookback" in drift_fields
    assert "live_stop_loss_price" in drift_fields


def test_run_validation_suite_builds_expected_sections():
    candidate = StrategyCandidate(
        strategy_id="S3",
        param_dict={
            "spike_threshold": 0.78,
            "spike_lookback": 15,
            "reversion_pct": 0.18,
            "min_reversion_sec": 45,
            "entry_window_start": 5,
            "entry_window_end": 120,
            "min_seconds_since_extremum": 2,
            "min_distance_from_mid": 0.08,
            "stop_loss": 0.20,
            "take_profit": 0.85,
        },
        config_id="S3_synthetic_candidate",
    )

    results = run_validation_suite(
        candidate,
        _synthetic_s3_markets(),
        base_slippage=0.0,
        slippage_grid=(0.0, 0.01),
        entry_delays=(0, 1),
        chronological_folds=2,
        bootstrap_iterations=50,
        include_neighbors=False,
    )

    assert results["overall"]["metrics"]["total_bets"] == 2
    assert len(results["slippage_sweep"]) == 2
    assert len(results["entry_delay_sweep"]) == 2
    assert len(results["chronological_folds"]) == 2
    assert len(results["asset_slices"]) == 3
    assert len(results["duration_slices"]) == 2
    assert len(results["day_slices"]) == 3
    assert results["bootstrap"]["iterations"] == 50
    assert results["parameter_neighbors"] == []

    markdown = render_validation_markdown(results)
    assert "## Slippage Sweep" in markdown
    assert "## Entry Delay Sweep" in markdown
    assert "## Chronological Folds" in markdown
