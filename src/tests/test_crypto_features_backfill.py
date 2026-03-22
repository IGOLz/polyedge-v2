from __future__ import annotations

import numpy as np

from shared.crypto_features import build_feature_series_from_rows
from shared.strategies.S17.config import get_default_config
from shared.strategies.S17.strategy import S17Strategy


def test_build_feature_series_from_rows_backfills_s17_required_features():
    prices = np.array([0.50, 0.56, 0.63, 0.71, 0.68, 0.62], dtype=float)
    feature_rows = [
        {"elapsed_second": idx, "underlying_close": close}
        for idx, close in enumerate([100.0, 100.2, 100.4, 100.7, 100.6, 100.5])
    ]

    feature_series = build_feature_series_from_rows(
        feature_rows,
        len(prices),
        prices=prices,
    )

    np.testing.assert_allclose(
        feature_series["market_up_delta_from_market_open"],
        np.array([0.0, 0.06, 0.13, 0.21, 0.18, 0.12], dtype=float),
    )
    np.testing.assert_allclose(
        feature_series["underlying_return_from_market_open"],
        np.array([0.0, 0.002, 0.004, 0.007, 0.006, 0.005], dtype=float),
        atol=1e-12,
    )
    np.testing.assert_allclose(
        feature_series["market_up_delta_5s"],
        np.array([np.nan, np.nan, np.nan, np.nan, np.nan, 0.12], dtype=float),
        equal_nan=True,
    )


def test_s17_market_becomes_eligible_after_backfill():
    prices = np.array([0.50, 0.56, 0.63, 0.71, 0.68, 0.62], dtype=float)
    feature_rows = [
        {"elapsed_second": idx, "underlying_close": close}
        for idx, close in enumerate([100.0, 100.2, 100.4, 100.7, 100.6, 100.5])
    ]
    market = {
        "feature_series": build_feature_series_from_rows(
            feature_rows,
            len(prices),
            prices=prices,
        )
    }

    strategy = S17Strategy(get_default_config())

    assert strategy.market_is_eligible(market) is True


def test_backfill_uses_first_finite_value_when_open_second_is_missing():
    prices = np.array([np.nan, 0.52, 0.58, 0.61, 0.59, 0.55], dtype=float)
    feature_rows = [
        {"elapsed_second": idx, "underlying_close": close}
        for idx, close in enumerate([np.nan, 100.0, 100.3, 100.6, 100.4, 100.2])
    ]

    feature_series = build_feature_series_from_rows(
        feature_rows,
        len(prices),
        prices=prices,
    )

    np.testing.assert_allclose(
        feature_series["market_up_delta_from_market_open"],
        np.array([np.nan, 0.0, 0.06, 0.09, 0.07, 0.03], dtype=float),
        atol=1e-12,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        feature_series["underlying_return_from_market_open"],
        np.array([np.nan, 0.0, 0.003, 0.006, 0.004, 0.002], dtype=float),
        atol=1e-12,
        equal_nan=True,
    )
