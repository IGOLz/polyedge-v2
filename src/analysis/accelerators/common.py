"""Shared numba helpers for accelerated strategy kernels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from analysis.backtest.engine import CRYPTO_FEE_EXPONENT, CRYPTO_FEE_RATE, _market_has_crypto_fees

try:
    from numba import njit

    NUMBA_AVAILABLE = True
    NUMBA_IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover
    NUMBA_AVAILABLE = False
    NUMBA_IMPORT_ERROR = str(exc)

    def njit(*args, **kwargs):
        def _decorator(fn):
            return fn

        return _decorator


@dataclass
class CommonPayload:
    """Compact shared market data for accelerated kernels."""

    prices: np.ndarray
    total_seconds: np.ndarray
    final_outcomes: np.ndarray
    asset_codes: np.ndarray
    duration_minutes: np.ndarray
    fee_active: np.ndarray
    hours: np.ndarray
    streak_directions: np.ndarray
    streak_lengths: np.ndarray


def build_common_payload(markets: list[dict]) -> CommonPayload:
    """Convert raw market dicts into common dense arrays."""
    max_seconds = max((market["total_seconds"] for market in markets), default=0)
    prices = np.full((len(markets), max_seconds), np.nan, dtype=np.float64)
    total_seconds = np.zeros(len(markets), dtype=np.int64)
    final_outcomes = np.zeros(len(markets), dtype=np.int8)
    duration_minutes = np.zeros(len(markets), dtype=np.int64)
    fee_active = np.zeros(len(markets), dtype=np.bool_)
    hours = np.full(len(markets), -1, dtype=np.int64)
    streak_directions = np.full(len(markets), -1, dtype=np.int64)
    streak_lengths = np.zeros(len(markets), dtype=np.int64)

    asset_labels = sorted({str(market["asset"]) for market in markets})
    asset_label_to_code = {label: idx for idx, label in enumerate(asset_labels)}
    asset_codes = np.zeros(len(markets), dtype=np.int64)

    for idx, market in enumerate(markets):
        price_array = np.asarray(market["prices"], dtype=np.float64)
        prices[idx, : price_array.shape[0]] = price_array
        total_seconds[idx] = int(market["total_seconds"])
        final_outcomes[idx] = 1 if market["final_outcome"] == "Up" else 0
        duration_minutes[idx] = int(market["duration_minutes"])
        asset_codes[idx] = asset_label_to_code[str(market["asset"])]
        fee_active[idx] = bool(_market_has_crypto_fees(market))
        hours[idx] = int(market.get("hour")) if market.get("hour") is not None else -1

        prior_direction = market.get("prior_market_type_streak_direction")
        if prior_direction == "Up":
            streak_directions[idx] = 1
        elif prior_direction == "Down":
            streak_directions[idx] = 0
        streak_lengths[idx] = int(market.get("prior_market_type_streak_length", 0) or 0)

    return CommonPayload(
        prices=prices,
        total_seconds=total_seconds,
        final_outcomes=final_outcomes,
        asset_codes=asset_codes,
        duration_minutes=duration_minutes,
        fee_active=fee_active,
        hours=hours,
        streak_directions=streak_directions,
        streak_lengths=streak_lengths,
    )


@njit(cache=True)
def precompute_nearest_prices_multi(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    tolerances: np.ndarray,
) -> np.ndarray:
    nearest = np.full((tolerances.shape[0], prices.shape[0], prices.shape[1]), np.nan)

    for tol_idx in range(tolerances.shape[0]):
        tolerance = int(tolerances[tol_idx])
        for market_idx in range(prices.shape[0]):
            market_total_seconds = total_seconds[market_idx]
            for sec in range(market_total_seconds):
                value = prices[market_idx, sec]
                if not np.isnan(value):
                    nearest[tol_idx, market_idx, sec] = value
                    continue

                for offset in range(1, tolerance + 1):
                    plus_idx = sec + offset
                    if plus_idx < market_total_seconds:
                        plus_value = prices[market_idx, plus_idx]
                        if not np.isnan(plus_value):
                            nearest[tol_idx, market_idx, sec] = plus_value
                            break

                    minus_idx = sec - offset
                    if minus_idx >= 0:
                        minus_value = prices[market_idx, minus_idx]
                        if not np.isnan(minus_value):
                            nearest[tol_idx, market_idx, sec] = minus_value
                            break

    return nearest


@njit(cache=True)
def polymarket_dynamic_fee_numba(
    price: float,
    shares: float = 1.0,
    fee_rate: float = CRYPTO_FEE_RATE,
    exponent: int = CRYPTO_FEE_EXPONENT,
) -> float:
    price = max(0.0, min(1.0, price))
    if shares <= 0.0 or price <= 0.0 or price >= 1.0:
        return 0.0

    fee_usdc = shares * price * fee_rate * (price * (1.0 - price)) ** exponent
    rounded = np.round(fee_usdc, 4)
    return rounded if rounded >= 0.0001 else 0.0


@njit(cache=True)
def resolve_trade_pnl(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    fee_active: np.ndarray,
    market_idx: int,
    entry_second: int,
    adjusted_entry: float,
    direction_up: bool,
    stop_loss: float,
    take_profit: float,
    entry_slippage: float = 0.0,
) -> tuple[float, float, float]:
    adjusted_entry = max(0.01, min(0.99, adjusted_entry + entry_slippage))
    entry_fee = 0.0
    exit_fee = 0.0
    net_shares = 1.0

    if fee_active[market_idx]:
        entry_fee = polymarket_dynamic_fee_numba(adjusted_entry, 1.0)
        if adjusted_entry > 0.0:
            fee_shares = entry_fee / adjusted_entry
            net_shares = max(0.0, 1.0 - fee_shares)

    exited_early = False
    pnl = 0.0
    if stop_loss > 0.0 and take_profit > 0.0:
        for sec in range(entry_second + 1, int(total_seconds[market_idx])):
            up_price = prices[market_idx, sec]
            if np.isnan(up_price):
                continue

            token_price = up_price if direction_up else 1.0 - up_price
            if token_price <= stop_loss or token_price >= take_profit:
                gross_proceeds = net_shares * token_price
                if fee_active[market_idx]:
                    exit_fee = polymarket_dynamic_fee_numba(token_price, net_shares)
                pnl = gross_proceeds - exit_fee - adjusted_entry
                exited_early = True
                break

    if not exited_early:
        won = (direction_up and final_outcomes[market_idx] == 1) or (
            (not direction_up) and final_outcomes[market_idx] == 0
        )
        if won:
            pnl = net_shares - adjusted_entry
        else:
            pnl = -adjusted_entry

    return np.round(pnl, 6), np.round(entry_fee, 6), np.round(exit_fee, 6)


@njit(cache=True)
def trailing_net_move_from_raw(prices: np.ndarray, market_idx: int, sec: int, lookback_seconds: int) -> float:
    start_sec = sec - lookback_seconds + 1
    if start_sec < 0:
        start_sec = 0

    first_value = np.nan
    last_value = np.nan
    valid_count = 0
    for pos in range(start_sec, sec + 1):
        value = prices[market_idx, pos]
        if np.isnan(value):
            continue
        if valid_count == 0:
            first_value = value
        last_value = value
        valid_count += 1

    if valid_count < 2:
        return np.nan
    return last_value - first_value
