"""Shared helpers for strategy implementations."""

from __future__ import annotations

import numpy as np


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
