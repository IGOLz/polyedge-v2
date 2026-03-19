"""Accelerated optimization kernel for strategy S1."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from analysis.accelerators.base import PrecomputedDataset, compute_metrics_from_arrays
from analysis.backtest.engine import (
    CRYPTO_FEE_EXPONENT,
    CRYPTO_FEE_RATE,
    Trade,
    _market_has_crypto_fees,
    make_trade,
)
from analysis.backtest_strategies import run_strategy
from shared.strategies.S1.config import get_default_config
from shared.strategies.S1.strategy import S1Strategy

try:
    from numba import njit

    NUMBA_AVAILABLE = True
    NUMBA_IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - exercised via availability checks
    NUMBA_AVAILABLE = False
    NUMBA_IMPORT_ERROR = str(exc)

    def njit(*args, **kwargs):
        def _decorator(fn):
            return fn

        return _decorator


@dataclass
class S1Payload:
    """Compact S1-specific market data used by the numba kernel."""

    prices: np.ndarray
    nearest_prices: np.ndarray
    trailing_moves: np.ndarray
    lookbacks: np.ndarray
    total_seconds: np.ndarray
    final_outcomes: np.ndarray
    asset_codes: np.ndarray
    duration_minutes: np.ndarray
    fee_active: np.ndarray


@njit(cache=True)
def _precompute_nearest_prices(prices: np.ndarray, total_seconds: np.ndarray, tolerance: int) -> np.ndarray:
    nearest = np.full(prices.shape, np.nan)
    market_count, max_seconds = prices.shape

    for market_idx in range(market_count):
        market_total_seconds = total_seconds[market_idx]
        for sec in range(market_total_seconds):
            value = prices[market_idx, sec]
            if not np.isnan(value):
                nearest[market_idx, sec] = value
                continue

            found = False
            for offset in range(1, tolerance + 1):
                plus_idx = sec + offset
                if plus_idx < market_total_seconds:
                    plus_value = prices[market_idx, plus_idx]
                    if not np.isnan(plus_value):
                        nearest[market_idx, sec] = plus_value
                        found = True
                        break

                minus_idx = sec - offset
                if minus_idx >= 0:
                    minus_value = prices[market_idx, minus_idx]
                    if not np.isnan(minus_value):
                        nearest[market_idx, sec] = minus_value
                        found = True
                        break

            if found:
                continue

    return nearest


@njit(cache=True)
def _precompute_trailing_moves(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    lookbacks: np.ndarray,
) -> np.ndarray:
    trailing = np.full((lookbacks.shape[0], prices.shape[0], prices.shape[1]), np.nan)

    for lookback_idx in range(lookbacks.shape[0]):
        lookback = int(lookbacks[lookback_idx])
        for market_idx in range(prices.shape[0]):
            market_total_seconds = total_seconds[market_idx]
            for sec in range(market_total_seconds):
                start_sec = sec - lookback + 1
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

                if valid_count >= 2:
                    trailing[lookback_idx, market_idx, sec] = last_value - first_value

    return trailing


@njit(cache=True)
def _polymarket_dynamic_fee_numba(
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
def _evaluate_s1_combo(
    prices: np.ndarray,
    nearest_prices: np.ndarray,
    trailing_moves: np.ndarray,
    lookbacks: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    entry_window_start = int(combo[0])
    entry_window_end = int(combo[1])
    price_low_threshold = combo[2]
    price_high_threshold = combo[3]
    min_deviation = combo[4]
    rebound_lookback = int(combo[5])
    rebound_min_move = combo[6]
    stop_loss = combo[7]
    take_profit = combo[8]

    lookback_idx = -1
    for idx in range(lookbacks.shape[0]):
        if int(lookbacks[idx]) == rebound_lookback:
            lookback_idx = idx
            break

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        market_total_seconds = int(total_seconds[market_idx])
        last_entry_second = min(entry_window_end, market_total_seconds - 1)
        if last_entry_second < entry_window_start:
            continue

        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1

        for sec in range(entry_window_start, last_entry_second + 1):
            price = nearest_prices[market_idx, sec]
            if np.isnan(price):
                continue

            recent_move = trailing_moves[lookback_idx, market_idx, sec]
            if np.isnan(recent_move):
                continue

            if price <= price_low_threshold and (0.50 - price) >= min_deviation:
                if recent_move >= rebound_min_move:
                    direction_up = True
                    adjusted_entry = max(0.01, min(0.99, price))
                    entry_second = sec
                    found = True
                    break

            if price >= price_high_threshold and (price - 0.50) >= min_deviation:
                if recent_move <= -rebound_min_move:
                    direction_up = False
                    adjusted_entry = max(0.01, min(0.99, 1.0 - price))
                    entry_second = sec
                    found = True
                    break

        if not found:
            continue

        adjusted_entry = max(0.01, min(0.99, adjusted_entry + entry_slippage))

        entry_fee = 0.0
        exit_fee = 0.0
        net_shares = 1.0
        if fee_active[market_idx]:
            entry_fee = _polymarket_dynamic_fee_numba(adjusted_entry, 1.0)
            if adjusted_entry > 0.0:
                fee_shares = entry_fee / adjusted_entry
                net_shares = max(0.0, 1.0 - fee_shares)

        pnl = 0.0
        exited_early = False
        if stop_loss > 0.0 and take_profit > 0.0:
            for sec in range(entry_second + 1, market_total_seconds):
                up_price = prices[market_idx, sec]
                if np.isnan(up_price):
                    continue

                token_price = up_price if direction_up else 1.0 - up_price
                if token_price <= stop_loss or token_price >= take_profit:
                    gross_proceeds = net_shares * token_price
                    if fee_active[market_idx]:
                        exit_fee = _polymarket_dynamic_fee_numba(token_price, net_shares)
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

        pnls[trade_count] = np.round(pnl, 6)
        entry_fees[trade_count] = np.round(entry_fee, 6)
        exit_fees[trade_count] = np.round(exit_fee, 6)
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return (
        pnls[:trade_count].copy(),
        entry_fees[:trade_count].copy(),
        exit_fees[:trade_count].copy(),
        trade_asset_codes[:trade_count].copy(),
        trade_durations[:trade_count].copy(),
    )


class S1Accelerator:
    """Generic-kernel implementation for S1 using numba."""

    strategy_id = "S1"

    def is_available(self) -> bool:
        return NUMBA_AVAILABLE

    def unavailable_reason(self) -> str:
        return NUMBA_IMPORT_ERROR or "Numba is not installed."

    def prepare(
        self,
        strategy_id: str,
        markets: list[dict],
        param_grid: dict[str, list],
    ) -> PrecomputedDataset:
        eligible_markets = list(markets)
        lookbacks = np.array(sorted(set(int(v) for v in param_grid["rebound_lookback"])), dtype=np.int64)
        max_seconds = max((market["total_seconds"] for market in eligible_markets), default=0)

        prices = np.full((len(eligible_markets), max_seconds), np.nan, dtype=np.float64)
        total_seconds = np.zeros(len(eligible_markets), dtype=np.int64)
        final_outcomes = np.zeros(len(eligible_markets), dtype=np.int8)
        duration_minutes = np.zeros(len(eligible_markets), dtype=np.int64)
        fee_active = np.zeros(len(eligible_markets), dtype=np.bool_)

        asset_labels = sorted({str(market["asset"]) for market in eligible_markets})
        asset_label_to_code = {label: idx for idx, label in enumerate(asset_labels)}
        asset_codes = np.zeros(len(eligible_markets), dtype=np.int64)

        for idx, market in enumerate(eligible_markets):
            price_array = np.asarray(market["prices"], dtype=np.float64)
            prices[idx, : price_array.shape[0]] = price_array
            total_seconds[idx] = int(market["total_seconds"])
            final_outcomes[idx] = 1 if market["final_outcome"] == "Up" else 0
            duration_minutes[idx] = int(market["duration_minutes"])
            asset_codes[idx] = asset_label_to_code[str(market["asset"])]
            fee_active[idx] = bool(_market_has_crypto_fees(market))

        nearest_prices = _precompute_nearest_prices(prices, total_seconds, 2)
        trailing_moves = _precompute_trailing_moves(prices, total_seconds, lookbacks)

        payload = S1Payload(
            prices=prices,
            nearest_prices=nearest_prices,
            trailing_moves=trailing_moves,
            lookbacks=lookbacks,
            total_seconds=total_seconds,
            final_outcomes=final_outcomes,
            asset_codes=asset_codes,
            duration_minutes=duration_minutes,
            fee_active=fee_active,
        )
        return PrecomputedDataset(
            strategy_id=strategy_id,
            markets=eligible_markets,
            payload=payload,
            eligible_markets=len(eligible_markets),
            skipped_markets_missing_features=0,
        )

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        return np.array(combo, dtype=np.float64)

    def evaluate_batch(
        self,
        dataset: PrecomputedDataset,
        encoded_batch: np.ndarray,
        combo_batch: list[tuple[object, ...]],
        param_names: list[str],
        config_id_builder,
    ) -> list[dict]:
        payload: S1Payload = dataset.payload
        results: list[dict] = []

        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s1_combo(
                payload.prices,
                payload.nearest_prices,
                payload.trailing_moves,
                payload.lookbacks,
                payload.total_seconds,
                payload.final_outcomes,
                payload.asset_codes,
                payload.duration_minutes,
                payload.fee_active,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(
                pnls=pnls,
                entry_fees=entry_fees,
                exit_fees=exit_fees,
                asset_codes=asset_codes,
                duration_minutes=durations,
                config_id=config_id,
            )
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)

        return results

    def materialize_trades(
        self,
        dataset: PrecomputedDataset,
        param_dict: dict[str, object],
        config_id: str,
    ) -> list[Trade]:
        base_config = get_default_config()
        strategy_params = {
            key: value
            for key, value in param_dict.items()
            if key in {field.name for field in dataclasses.fields(type(base_config))}
        }
        exit_params = {key: value for key, value in param_dict.items() if key not in strategy_params}
        strategy = S1Strategy(dataclasses.replace(base_config, **strategy_params))
        trades, _ = run_strategy(
            config_id,
            strategy,
            dataset.markets,
            slippage=dataset.slippage,
            stop_loss=exit_params.get("stop_loss"),
            take_profit=exit_params.get("take_profit"),
            log_summary=False,
        )
        return trades
