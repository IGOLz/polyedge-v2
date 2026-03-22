from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from analysis.meta_tree import ExpectedPnlTreeRegressor, TabularFeatureEncoder
from shared.strategies import MarketSnapshot, Signal
from trading.db import MarketInfo
from trading.meta_selector import LiveMetaSelector


def test_encoder_and_tree_payload_round_trip_preserve_predictions():
    df = pd.DataFrame(
        {
            "feature_one": [0.0, 0.1, 0.9, 1.0],
            "strategy_id": ["S14", "S14", "S15", "S15"],
            "asset": ["btc", "btc", "btc", "btc"],
            "direction": ["Up", "Down", "Up", "Down"],
        }
    )
    y = np.array([-0.4, -0.1, 0.5, 0.7], dtype=float)

    encoder = TabularFeatureEncoder()
    X = encoder.fit_transform(df)
    model = ExpectedPnlTreeRegressor(max_depth=2, min_samples_leaf=1)
    model.fit(X, y)

    restored_encoder = TabularFeatureEncoder.from_payload(encoder.to_payload())
    restored_model = ExpectedPnlTreeRegressor.from_payload(
        model.to_payload(feature_names=encoder.feature_names_)
    )

    original_predictions = model.predict(X)
    restored_predictions = restored_model.predict(restored_encoder.transform(df))
    assert np.allclose(original_predictions, restored_predictions)


def test_live_meta_selector_prefers_higher_scoring_signal(tmp_path):
    training = pd.DataFrame(
        {
            "strategy_id": ["S14", "S14", "S15", "S15"],
            "asset": ["btc", "btc", "btc", "btc"],
            "direction": ["Up", "Down", "Up", "Down"],
            "direction_sign": [1, -1, 1, -1],
            "hour": [18, 18, 18, 18],
            "duration_minutes": [5, 5, 5, 5],
            "signal_entry_price": [0.50, 0.50, 0.50, 0.50],
            "entry_second": [45, 45, 45, 45],
            "remaining_seconds": [254, 254, 254, 254],
            "same_second_signal_count": [2, 2, 2, 2],
            "same_second_up_signals": [1, 1, 1, 1],
            "same_second_down_signals": [1, 1, 1, 1],
            "peer_same_direction_count": [0, 0, 0, 0],
            "peer_opposite_direction_count": [1, 1, 1, 1],
            "market_price_distance_from_mid": [0.02, 0.02, 0.02, 0.02],
            "signal_trade_count": [0.0, 0.0, 120.0, 120.0],
            "signal_market_delta": [0.0, 0.0, 0.0, 0.0],
        }
    )
    target = np.array([-0.4, -0.2, 0.6, 0.7], dtype=float)
    encoder = TabularFeatureEncoder()
    model = ExpectedPnlTreeRegressor(max_depth=1, min_samples_leaf=1)
    model.fit(encoder.fit_transform(training), target)

    bundle_path = tmp_path / "deploy_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "experts": ["S14", "S15"],
                "deployment": {
                    "recommended_threshold": 0.0,
                    "encoder": encoder.to_payload(),
                    "model": model.to_payload(feature_names=encoder.feature_names_),
                },
            }
        ),
        encoding="utf-8",
    )

    selector = LiveMetaSelector.from_bundle_path(bundle_path)
    market = MarketInfo(
        market_id="m1",
        market_type="btc_5m",
        started_at=datetime(2026, 3, 22, 18, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 22, 18, 5, tzinfo=timezone.utc),
    )
    prices = np.full(60, 0.52, dtype=float)
    snapshot = MarketSnapshot(
        market_id="m1",
        market_type="btc_5m",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=45,
        metadata={"asset": "btc", "duration_minutes": 5, "hour": 18},
    )
    s14 = Signal(
        direction="Down",
        strategy_name="S14_divergence_fade",
        entry_price=0.48,
        signal_data={
            "entry_second": 45,
            "observed_up_price": 0.52,
            "market_delta": 0.08,
            "trade_count": 0,
        },
    )
    s15 = Signal(
        direction="Up",
        strategy_name="S15_breakout_confirmed",
        entry_price=0.52,
        signal_data={"entry_second": 45, "observed_up_price": 0.52, "trade_count": 120},
    )

    selected, scored = selector.pick_signal(market, snapshot, [s14, s15])

    assert selected is s15
    assert scored
    s15_row = next(row for row in scored if row["strategy_id"] == "S15")
    assert float(s15_row["predicted_pnl"]) > 0.0
