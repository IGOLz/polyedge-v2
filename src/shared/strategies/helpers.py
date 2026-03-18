"""Shared helpers for strategy implementations."""

from __future__ import annotations

import numpy as np

from shared.strategies.base import MarketSnapshot


def get_price(
    prices: np.ndarray,
    target_sec: int,
    tolerance: int = 5,
) -> float | None:
    """Return the nearest valid price around ``target_sec`` within tolerance."""
    if target_sec < 0 or target_sec >= len(prices):
        return None

    value = prices[target_sec]
    if not np.isnan(value):
        return float(value)

    for offset in range(1, tolerance + 1):
        plus_idx = target_sec + offset
        if plus_idx < len(prices):
            value = prices[plus_idx]
            if not np.isnan(value):
                return float(value)

        minus_idx = target_sec - offset
        if minus_idx >= 0:
            value = prices[minus_idx]
            if not np.isnan(value):
                return float(value)

    return None


def current_second(snapshot: MarketSnapshot) -> int:
    """Return the current evaluation second for a history-only snapshot."""
    if len(snapshot.prices) == 0:
        return -1
    return min(len(snapshot.prices) - 1, int(snapshot.elapsed_seconds))


def to_token_price(up_price: float, direction: str) -> float:
    """Convert observed up-price into the token price for ``direction``."""
    return up_price if direction == "Up" else 1.0 - up_price


def valid_points(
    prices: np.ndarray,
    start_sec: int,
    end_sec: int,
) -> list[tuple[int, float]]:
    """Return valid ``(second, price)`` pairs in the inclusive window."""
    if len(prices) == 0:
        return []

    start_sec = max(0, start_sec)
    end_sec = min(end_sec, len(prices) - 1)
    if start_sec > end_sec:
        return []

    points: list[tuple[int, float]] = []
    for sec in range(start_sec, end_sec + 1):
        value = prices[sec]
        if not np.isnan(value):
            points.append((sec, float(value)))
    return points


def trailing_points(
    prices: np.ndarray,
    end_sec: int,
    lookback_seconds: int,
) -> list[tuple[int, float]]:
    """Return valid points ending at ``end_sec`` over a trailing window."""
    return valid_points(prices, end_sec - lookback_seconds + 1, end_sec)


def trailing_values(
    prices: np.ndarray,
    end_sec: int,
    lookback_seconds: int,
) -> np.ndarray:
    """Return trailing valid price values ending at ``end_sec``."""
    points = trailing_points(prices, end_sec, lookback_seconds)
    return np.array([price for _, price in points], dtype=float)


def trailing_net_move(
    prices: np.ndarray,
    end_sec: int,
    lookback_seconds: int,
) -> float | None:
    """Return net move across a trailing window, or ``None`` if insufficient."""
    values = trailing_values(prices, end_sec, lookback_seconds)
    if len(values) < 2:
        return None
    return float(values[-1] - values[0])


def realized_volatility(values: np.ndarray) -> float:
    """Return standard deviation of 1-step changes for ``values``."""
    if len(values) < 3:
        return 0.0
    diffs = np.diff(values)
    if len(diffs) < 2:
        return 0.0
    return float(np.std(diffs, ddof=1))


def path_efficiency(values: np.ndarray) -> float:
    """Return directional efficiency in ``[0, 1]`` for a price path."""
    if len(values) < 2:
        return 0.0

    path_length = float(np.sum(np.abs(np.diff(values))))
    if path_length <= 1e-9:
        return 0.0

    net_move = float(values[-1] - values[0])
    return abs(net_move) / path_length


def direction_flips(values: np.ndarray, noise_threshold: float = 0.002) -> int:
    """Count directional sign changes while ignoring tiny moves."""
    if len(values) < 3:
        return 0

    last_sign = 0
    flips = 0
    for delta in np.diff(values):
        if abs(delta) <= noise_threshold:
            continue
        sign = 1 if delta > 0 else -1
        if last_sign != 0 and sign != last_sign:
            flips += 1
        last_sign = sign
    return flips


def get_feature_series(
    snapshot: MarketSnapshot,
    name: str,
) -> np.ndarray | None:
    """Return a feature array from ``snapshot.feature_series`` if available."""
    series = snapshot.feature_series.get(name)
    if series is None:
        return None
    return series


def get_feature_value(
    snapshot: MarketSnapshot,
    name: str,
    target_sec: int | None = None,
    tolerance: int = 0,
) -> float | None:
    """Return a feature value with optional tolerance lookup."""
    series = get_feature_series(snapshot, name)
    if series is None:
        return None

    if target_sec is None:
        target_sec = current_second(snapshot)
    return get_price(series, target_sec, tolerance=tolerance)


def get_window_feature_value(
    snapshot: MarketSnapshot,
    prefix: str,
    window_seconds: int,
    target_sec: int | None = None,
) -> float | None:
    """Return a windowed feature such as ``underlying_return_10s``."""
    if window_seconds not in {5, 10, 30}:
        raise ValueError(f"Unsupported window: {window_seconds}")
    return get_feature_value(snapshot, f"{prefix}_{window_seconds}s", target_sec=target_sec)
