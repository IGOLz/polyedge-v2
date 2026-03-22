"""Shared feature engineering for expert-signal opportunity rows."""

from __future__ import annotations

from typing import Any

import numpy as np

from shared.strategies.base import Signal
from shared.strategies.helpers import (
    direction_flips,
    get_price,
    path_efficiency,
    realized_volatility,
    trailing_values,
)

NUMERIC_SIGNAL_KEYS = {
    "cross_move",
    "direction_mismatch",
    "market_delta",
    "observed_up_price",
    "previous_up_price",
    "recent_move",
    "trade_count",
    "underlying_return",
    "underlying_vol",
}

FEATURE_COLUMNS = (
    "market_up_delta_from_market_open",
    "market_up_delta_5s",
    "market_up_delta_10s",
    "market_up_delta_30s",
    "underlying_return_from_market_open",
    "underlying_return_5s",
    "underlying_return_10s",
    "underlying_return_30s",
    "underlying_realized_vol_10s",
    "underlying_realized_vol_30s",
    "underlying_trade_count",
    "direction_mismatch_market_open",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
)


def strategy_id_from_name(strategy_name: str) -> str:
    """Derive the short strategy id from a strategy name."""
    if not strategy_name:
        return ""
    return strategy_name.split("_", 1)[0].strip()


def to_float(value: Any) -> float:
    """Convert *value* to float, returning NaN when conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def numeric_signal_payload(signal: Signal) -> dict[str, float]:
    """Extract numeric signal payload fields used by the selector."""
    payload: dict[str, float] = {}
    for key in NUMERIC_SIGNAL_KEYS:
        if key in signal.signal_data:
            payload[f"signal_{key}"] = to_float(signal.signal_data[key])
    return payload


def feature_value(
    feature_series: dict[str, np.ndarray] | None,
    name: str,
    second: int,
    tolerance: int = 0,
) -> float:
    """Return a per-second feature value or NaN when unavailable."""
    if feature_series is None:
        return float("nan")
    series = feature_series.get(name)
    if series is None:
        return float("nan")
    value = get_price(series, second, tolerance=tolerance)
    if value is None:
        return float("nan")
    return float(value)


def trailing_context(prices: np.ndarray, second: int, window: int) -> dict[str, float]:
    """Return trailing-path summary features for *prices* ending at *second*."""
    values = trailing_values(prices, second, window)
    if len(values) == 0:
        return {
            f"market_valid_points_{window}s": 0.0,
            f"market_net_move_{window}s": float("nan"),
            f"market_realized_vol_{window}s": float("nan"),
            f"market_path_efficiency_{window}s": float("nan"),
            f"market_direction_flips_{window}s": float("nan"),
        }

    net_move = float(values[-1] - values[0]) if len(values) >= 2 else float("nan")
    return {
        f"market_valid_points_{window}s": float(len(values)),
        f"market_net_move_{window}s": net_move,
        f"market_realized_vol_{window}s": realized_volatility(values),
        f"market_path_efficiency_{window}s": path_efficiency(values),
        f"market_direction_flips_{window}s": float(direction_flips(values)),
    }


def context_features(
    *,
    prices: np.ndarray,
    feature_series: dict[str, np.ndarray] | None,
    total_seconds: int,
    second: int,
    second_signals: dict[str, Signal],
) -> dict[str, Any]:
    """Build market-context features shared by research and live scoring."""
    observed_up_price = get_price(prices, second, tolerance=1)
    observed_up_price = float("nan") if observed_up_price is None else float(observed_up_price)
    up_signals = sum(1 for signal in second_signals.values() if signal.direction == "Up")
    down_signals = sum(1 for signal in second_signals.values() if signal.direction == "Down")

    context = {
        "entry_second": second,
        "remaining_seconds": int(total_seconds - 1 - second),
        "observed_up_price": observed_up_price,
        "market_price_distance_from_mid": abs(observed_up_price - 0.50)
        if np.isfinite(observed_up_price)
        else float("nan"),
        "same_second_signal_count": len(second_signals),
        "same_second_up_signals": up_signals,
        "same_second_down_signals": down_signals,
    }

    for feature_name in FEATURE_COLUMNS:
        context[feature_name] = feature_value(
            feature_series,
            feature_name,
            second,
            tolerance=0,
        )

    for window in (5, 10, 30):
        context.update(trailing_context(prices, second, window))

    return context
