"""Shared crypto feature definitions and live feature-series builders."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

CRYPTO_FEATURE_COLUMNS = [
    "market_up_price_market_open",
    "market_up_delta_from_market_open",
    "market_up_delta_5s",
    "market_up_delta_10s",
    "market_up_delta_30s",
    "underlying_bar_open",
    "underlying_bar_high",
    "underlying_bar_low",
    "underlying_close",
    "underlying_volume",
    "underlying_quote_volume",
    "underlying_trade_count",
    "underlying_taker_buy_base_volume",
    "underlying_taker_buy_quote_volume",
    "underlying_market_open_close",
    "underlying_return_from_market_open",
    "underlying_return_5s",
    "underlying_return_10s",
    "underlying_return_30s",
    "underlying_realized_vol_10s",
    "underlying_realized_vol_30s",
    "direction_mismatch_market_open",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
]

BOOL_FEATURE_COLUMNS = {
    "direction_mismatch_market_open",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
}

SUPPORTED_LIVE_FEATURE_COLUMNS = set(CRYPTO_FEATURE_COLUMNS)


def build_feature_series_from_rows(
    feature_rows: list[dict],
    total_seconds: int,
) -> dict[str, np.ndarray]:
    if not feature_rows:
        return {}

    feature_series = {
        column: np.full(total_seconds, np.nan, dtype=float)
        for column in CRYPTO_FEATURE_COLUMNS
    }

    for row in feature_rows:
        second = int(row["elapsed_second"])
        if second < 0 or second >= total_seconds:
            continue

        for column in CRYPTO_FEATURE_COLUMNS:
            value = row.get(column)
            if value is None:
                continue
            if column in BOOL_FEATURE_COLUMNS:
                feature_series[column][second] = 1.0 if value else 0.0
            else:
                feature_series[column][second] = float(value)

    return feature_series


def build_live_feature_series(
    *,
    prices: np.ndarray,
    crypto_rows: list[dict],
    started_at: datetime,
) -> dict[str, np.ndarray]:
    total_seconds = len(prices)
    if total_seconds == 0:
        return {}

    feature_series = {
        column: np.full(total_seconds, np.nan, dtype=float)
        for column in CRYPTO_FEATURE_COLUMNS
    }

    for row in crypto_rows:
        row_time = row.get("time")
        if row_time is None:
            continue
        elapsed_second = int((row_time - started_at).total_seconds())
        if elapsed_second < 0 or elapsed_second >= total_seconds:
            continue

        _assign_float(feature_series["underlying_bar_open"], elapsed_second, row.get("open"))
        _assign_float(feature_series["underlying_bar_high"], elapsed_second, row.get("high"))
        _assign_float(feature_series["underlying_bar_low"], elapsed_second, row.get("low"))
        _assign_float(feature_series["underlying_close"], elapsed_second, row.get("close"))
        _assign_float(feature_series["underlying_volume"], elapsed_second, row.get("volume"))
        _assign_float(
            feature_series["underlying_quote_volume"], elapsed_second, row.get("quote_volume")
        )
        _assign_float(
            feature_series["underlying_trade_count"], elapsed_second, row.get("trade_count")
        )
        _assign_float(
            feature_series["underlying_taker_buy_base_volume"],
            elapsed_second,
            row.get("taker_buy_base_volume"),
        )
        _assign_float(
            feature_series["underlying_taker_buy_quote_volume"],
            elapsed_second,
            row.get("taker_buy_quote_volume"),
        )

    _populate_market_features(feature_series, prices)
    _populate_underlying_features(feature_series)
    _populate_direction_mismatch_features(feature_series)
    return feature_series


def latest_bar_is_fresh(
    latest_bar_time: datetime | None,
    *,
    now: datetime | None = None,
    threshold_seconds: int = 3,
) -> bool:
    if latest_bar_time is None:
        return False

    utc_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected_bar_time = utc_now.replace(microsecond=0)
    age_seconds = (expected_bar_time - latest_bar_time.astimezone(timezone.utc)).total_seconds()
    return age_seconds <= threshold_seconds


def _assign_float(series: np.ndarray, idx: int, value) -> None:
    if value is None:
        return
    series[idx] = float(value)


def _populate_market_features(feature_series: dict[str, np.ndarray], prices: np.ndarray) -> None:
    market_open = float(prices[0]) if len(prices) > 0 and np.isfinite(prices[0]) else np.nan
    if np.isfinite(market_open):
        feature_series["market_up_price_market_open"].fill(market_open)

    feature_series["market_up_delta_from_market_open"][:] = _delta_from_base(prices, market_open)
    feature_series["market_up_delta_5s"][:] = _window_delta(prices, 5)
    feature_series["market_up_delta_10s"][:] = _window_delta(prices, 10)
    feature_series["market_up_delta_30s"][:] = _window_delta(prices, 30)


def _populate_underlying_features(feature_series: dict[str, np.ndarray]) -> None:
    close_series = feature_series["underlying_close"]
    open_close = float(close_series[0]) if len(close_series) > 0 and np.isfinite(close_series[0]) else np.nan
    if np.isfinite(open_close):
        feature_series["underlying_market_open_close"].fill(open_close)

    feature_series["underlying_return_from_market_open"][:] = _return_from_base(
        close_series, open_close
    )
    feature_series["underlying_return_5s"][:] = _window_return(close_series, 5)
    feature_series["underlying_return_10s"][:] = _window_return(close_series, 10)
    feature_series["underlying_return_30s"][:] = _window_return(close_series, 30)

    log_returns = np.full(len(close_series), np.nan, dtype=float)
    for idx in range(1, len(close_series)):
        prev = close_series[idx - 1]
        curr = close_series[idx]
        if np.isfinite(prev) and np.isfinite(curr) and prev > 0.0 and curr > 0.0:
            log_returns[idx] = float(np.log(curr / prev))

    feature_series["underlying_realized_vol_10s"][:] = _rolling_sample_std(log_returns, 10)
    feature_series["underlying_realized_vol_30s"][:] = _rolling_sample_std(log_returns, 30)


def _populate_direction_mismatch_features(feature_series: dict[str, np.ndarray]) -> None:
    feature_series["direction_mismatch_market_open"][:] = _direction_mismatch(
        feature_series["market_up_delta_from_market_open"],
        feature_series["underlying_return_from_market_open"],
    )
    feature_series["direction_mismatch_5s"][:] = _direction_mismatch(
        feature_series["market_up_delta_5s"],
        feature_series["underlying_return_5s"],
    )
    feature_series["direction_mismatch_10s"][:] = _direction_mismatch(
        feature_series["market_up_delta_10s"],
        feature_series["underlying_return_10s"],
    )
    feature_series["direction_mismatch_30s"][:] = _direction_mismatch(
        feature_series["market_up_delta_30s"],
        feature_series["underlying_return_30s"],
    )


def _delta_from_base(values: np.ndarray, base_value: float) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    if not np.isfinite(base_value):
        return result
    for idx, value in enumerate(values):
        if np.isfinite(value):
            result[idx] = float(value - base_value)
    return result


def _window_delta(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    for idx in range(window, len(values)):
        curr = values[idx]
        prev = values[idx - window]
        if np.isfinite(curr) and np.isfinite(prev):
            result[idx] = float(curr - prev)
    return result


def _return_from_base(values: np.ndarray, base_value: float) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    if not np.isfinite(base_value) or base_value <= 0.0:
        return result
    for idx, value in enumerate(values):
        if np.isfinite(value) and value > 0.0:
            result[idx] = float((value / base_value) - 1.0)
    return result


def _window_return(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    for idx in range(window, len(values)):
        curr = values[idx]
        prev = values[idx - window]
        if np.isfinite(curr) and np.isfinite(prev) and curr > 0.0 and prev > 0.0:
            result[idx] = float((curr / prev) - 1.0)
    return result


def _rolling_sample_std(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    for idx in range(len(values)):
        start = max(0, idx - window + 1)
        sample = values[start : idx + 1]
        sample = sample[np.isfinite(sample)]
        if len(sample) >= 2:
            result[idx] = float(np.std(sample, ddof=1))
    return result


def _direction_mismatch(
    market_delta: np.ndarray,
    underlying_return: np.ndarray,
) -> np.ndarray:
    result = np.full(len(market_delta), np.nan, dtype=float)
    for idx in range(len(market_delta)):
        delta = market_delta[idx]
        ret = underlying_return[idx]
        if not np.isfinite(delta) or not np.isfinite(ret):
            continue
        if abs(delta) < 1e-12 or abs(ret) < 1e-12:
            continue
        result[idx] = 1.0 if np.sign(delta) != np.sign(ret) else 0.0
    return result
