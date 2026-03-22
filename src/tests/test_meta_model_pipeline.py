from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analysis.meta_tree import (
    ExpectedPnlTreeRegressor,
    apply_selection_policy,
    choose_prediction_threshold,
)
from analysis.opportunity_dataset import build_opportunity_dataset
from analysis.train_meta_model import run_meta_model_pipeline
from analysis.walkforward import apply_walkforward_split, build_embargoed_walkforward_splits


def _make_market(
    market_id: str,
    *,
    started_at: datetime,
    prices: np.ndarray,
    final_outcome: str,
) -> dict:
    total_seconds = len(prices)
    underlying_return_5s = np.full(total_seconds, np.nan, dtype=float)
    underlying_trade_count = np.full(total_seconds, np.nan, dtype=float)
    for second in range(5, total_seconds):
        underlying_return_5s[second] = 0.002
        underlying_trade_count[second] = 100.0

    return {
        "market_id": market_id,
        "market_type": "btc_5m",
        "asset": "btc",
        "duration_minutes": 5,
        "total_seconds": total_seconds,
        "started_at": started_at,
        "ended_at": started_at + timedelta(seconds=total_seconds),
        "final_outcome": final_outcome,
        "hour": started_at.hour,
        "prices": prices,
        "feature_series": {
            "underlying_return_5s": underlying_return_5s,
            "underlying_trade_count": underlying_trade_count,
        },
    }


def _s5_and_s15_market(started_at: datetime, *, market_id: str, final_outcome: str) -> dict:
    prices = np.full(300, 0.44, dtype=float)
    prices[:30] = 0.44
    prices[30:45] = np.linspace(0.44, 0.50, 15)
    prices[45] = 0.53
    prices[46:] = 0.72 if final_outcome == "Up" else 0.28
    return _make_market(
        market_id,
        started_at=started_at,
        prices=prices,
        final_outcome=final_outcome,
    )


def test_build_opportunity_dataset_captures_expert_signal_rows():
    started_at = datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc)
    dataset = build_opportunity_dataset(
        [_s5_and_s15_market(started_at, market_id="m1", final_outcome="Up")],
        expert_ids=("S5", "S15"),
        config_source="candidate",
        slippage=0.0,
    )

    assert set(dataset["strategy_id"]) == {"S5", "S15"}
    assert (dataset["duration_minutes"] == 5).all()
    assert (dataset["realized_pnl"] > 0).all()
    assert (dataset["same_second_signal_count"] >= 1).all()


def test_build_embargoed_walkforward_splits_respects_day_boundaries():
    base = datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc)
    rows = []
    for offset in range(7):
        day = (base + timedelta(days=offset)).date().isoformat()
        rows.append(
            {
                "market_day": day,
                "started_at": base + timedelta(days=offset),
                "realized_pnl": float(offset),
            }
        )
    df = pd.DataFrame(rows)

    splits = build_embargoed_walkforward_splits(
        df,
        train_days=3,
        validation_days=1,
        embargo_days=1,
        test_days=1,
        step_days=1,
    )

    assert len(splits) == 2
    train_df, validation_df, test_df = apply_walkforward_split(df, splits[0])
    assert set(train_df["market_day"]) == set(splits[0].train_days)
    assert set(validation_df["market_day"]) == set(splits[0].validation_days)
    assert set(test_df["market_day"]) == set(splits[0].test_days)
    assert not set(splits[0].test_days) & set(splits[0].embargo_days)


def test_expected_pnl_tree_regressor_learns_simple_threshold():
    x = np.array([[0.0], [0.2], [0.8], [1.0], [1.2], [1.4]], dtype=float)
    y = np.array([-1.0, -0.8, 0.5, 0.8, 1.0, 1.1], dtype=float)

    model = ExpectedPnlTreeRegressor(max_depth=1, min_samples_leaf=2)
    model.fit(x, y)
    predictions = model.predict(x)

    assert predictions[0] < 0.0
    assert predictions[-1] > 0.0


def test_choose_prediction_threshold_prefers_positive_pnl_selection():
    df = pd.DataFrame(
        {
            "market_id": ["m1", "m2", "m3", "m4"],
            "asset": ["btc", "btc", "btc", "btc"],
            "duration_minutes": [5, 5, 5, 5],
            "realized_pnl": [-0.4, 0.2, 0.5, 0.6],
            "entry_fee_usdc": [0.0, 0.0, 0.0, 0.0],
            "exit_fee_usdc": [0.0, 0.0, 0.0, 0.0],
        }
    )
    predictions = np.array([-0.3, 0.1, 0.4, 0.5], dtype=float)

    threshold, metrics, _ = choose_prediction_threshold(df, predictions, min_trades=2)

    assert threshold >= 0.0
    assert metrics["total_pnl"] > 0.0


def test_apply_selection_policy_limits_rows_per_day():
    df = pd.DataFrame(
        {
            "market_day": ["2026-03-19", "2026-03-19", "2026-03-19", "2026-03-20", "2026-03-20"],
            "market_id": ["m1", "m2", "m3", "m4", "m5"],
            "predicted_pnl": [0.10, 0.08, 0.02, 0.20, 0.05],
            "predicted_positive_rate": [0.9, 0.7, 0.6, 0.95, 0.65],
        }
    )

    selected, summary = apply_selection_policy(
        df,
        threshold=0.0,
        min_threshold=0.0,
        top_k_per_day=1,
    )

    assert summary["rows_after_threshold"] == 5
    assert summary["rows_after_policy"] == 2
    assert list(selected["market_id"]) == ["m1", "m4"]


def test_run_meta_model_pipeline_produces_split_results():
    base = datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc)
    markets = [
        _s5_and_s15_market(base + timedelta(days=offset), market_id=f"market_{offset}", final_outcome="Up")
        for offset in range(6)
    ]
    dataset = build_opportunity_dataset(
        markets,
        expert_ids=("S5", "S15"),
        config_source="candidate",
        slippage=0.0,
    )

    results = run_meta_model_pipeline(
        dataset,
        train_days=2,
        validation_days=1,
        embargo_days=1,
        test_days=1,
        step_days=1,
        max_depth=2,
        min_samples_leaf=2,
        min_validation_trades=1,
        min_threshold=0.0,
        top_k_per_day=1,
        top_percent_per_day=None,
    )

    assert results["dataset"]["rows"] == len(dataset)
    assert len(results["splits"]) >= 1
    assert results["overall"]["selector_metrics"]["total_bets"] >= 1
    assert results["overall"]["all_signal_metrics"]["total_bets"] == len(results["predictions"])
    assert results["overall"]["comparison"]["trade_retain_pct"] <= 100.0
