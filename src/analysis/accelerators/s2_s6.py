"""Accelerated optimization kernels for strategies S2 through S6."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from analysis.accelerators.base import PrecomputedDataset, compute_metrics_from_arrays
from analysis.accelerators.common import (
    NUMBA_AVAILABLE,
    NUMBA_IMPORT_ERROR,
    build_common_payload,
    njit,
    precompute_nearest_prices_multi,
    resolve_trade_pnl,
    trailing_net_move_from_raw,
)
from analysis.backtest.engine import Trade
from analysis.backtest_strategies import run_strategy
from shared.strategies.S2.config import get_default_config as get_s2_default_config
from shared.strategies.S2.strategy import S2Strategy
from shared.strategies.S3.config import get_default_config as get_s3_default_config
from shared.strategies.S3.strategy import S3Strategy
from shared.strategies.S4.config import get_default_config as get_s4_default_config
from shared.strategies.S4.strategy import S4Strategy
from shared.strategies.S5.config import get_default_config as get_s5_default_config
from shared.strategies.S5.strategy import S5Strategy
from shared.strategies.S6.config import get_default_config as get_s6_default_config
from shared.strategies.S6.strategy import S6Strategy


@dataclass
class WindowPayload:
    common: object
    nearest_prices: np.ndarray


@dataclass
class S5Payload:
    common: object
    nearest_prices: np.ndarray
    encoded_hour_options: np.ndarray


@njit(cache=True)
def _get_tolerance_index(tolerances: np.ndarray, tolerance: int) -> int:
    for idx in range(tolerances.shape[0]):
        if int(tolerances[idx]) == tolerance:
            return idx
    return 0


@njit(cache=True)
def _evaluate_s2_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_prices: np.ndarray,
    tolerances: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    eval_window_start = int(combo[0])
    eval_window_end = int(combo[1])
    momentum_threshold = combo[2]
    tolerance = int(combo[3])
    max_entry_second = int(combo[4])
    efficiency_min = combo[5]
    min_distance_from_mid = combo[6]
    stop_loss = combo[7]
    take_profit = combo[8]

    tol_idx = _get_tolerance_index(tolerances, tolerance)
    lookback = max(1, eval_window_end - eval_window_start)

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        last_entry_second = min(max_entry_second, int(total_seconds[market_idx]) - 1)
        if last_entry_second < eval_window_end:
            continue

        found = False
        adjusted_entry = 0.0
        direction_up = True
        entry_second = -1

        for sec in range(eval_window_end, last_entry_second + 1):
            start_sec = sec - lookback
            if start_sec < 0:
                start_sec = 0

            first_value = np.nan
            last_value = np.nan
            valid_count = 0
            path_length = 0.0
            prev_value = np.nan
            for pos in range(start_sec, sec + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                if valid_count == 0:
                    first_value = value
                else:
                    path_length += abs(value - prev_value)
                prev_value = value
                last_value = value
                valid_count += 1

            if valid_count < 4:
                continue

            net_move = last_value - first_value
            if abs(net_move) < momentum_threshold:
                continue

            efficiency = 0.0
            if path_length > 1e-9:
                efficiency = abs(net_move) / path_length
            if efficiency < efficiency_min:
                continue

            price = nearest_prices[tol_idx, market_idx, sec]
            if np.isnan(price) or abs(price - 0.50) < min_distance_from_mid:
                continue

            direction_up = net_move > 0
            adjusted_entry = max(0.01, min(0.99, price if direction_up else 1.0 - price))
            entry_second = sec
            found = True
            break

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s3_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_prices: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    spike_threshold = combo[0]
    spike_lookback = int(combo[1])
    reversion_pct = combo[2]
    min_reversion_sec = int(combo[3])
    entry_window_start = int(combo[4])
    entry_window_end = int(combo[5])
    min_seconds_since_extremum = int(combo[6])
    min_distance_from_mid = combo[7]
    stop_loss = combo[8]
    take_profit = combo[9]

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        found = False
        adjusted_entry = 0.0
        direction_up = True
        entry_second = -1
        market_total_seconds = int(total_seconds[market_idx])

        last_entry_second = min(entry_window_end, market_total_seconds - 1)
        if last_entry_second < entry_window_start:
            continue

        for sec in range(max(1, entry_window_start), last_entry_second + 1):
            current_price = nearest_prices[market_idx, sec]
            if np.isnan(current_price):
                continue
            if abs(current_price - 0.50) < min_distance_from_mid:
                continue

            window_start = sec - (spike_lookback + min_reversion_sec)
            if window_start < 0:
                window_start = 0

            peak_price = -1.0
            peak_sec = -1
            trough_price = 2.0
            trough_sec = -1
            valid_count = 0

            for pos in range(window_start, sec):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                valid_count += 1
                if value > peak_price:
                    peak_price = value
                    peak_sec = pos
                if value < trough_price:
                    trough_price = value
                    trough_sec = pos

            if valid_count < 6:
                continue

            best_reversion = -1.0
            chosen_direction = 0

            elapsed_since_peak = sec - peak_sec
            if (
                peak_price >= spike_threshold
                and peak_sec >= 0
                and min_seconds_since_extremum <= elapsed_since_peak <= min_reversion_sec
            ):
                reversion_amount = (peak_price - current_price) / peak_price if peak_price > 0.0 else 0.0
                if reversion_amount >= reversion_pct and current_price < peak_price and current_price > 0.50:
                    best_reversion = reversion_amount
                    chosen_direction = 0

            lower_threshold = 1.0 - spike_threshold
            elapsed_since_trough = sec - trough_sec
            if (
                trough_price <= lower_threshold
                and trough_sec >= 0
                and min_seconds_since_extremum <= elapsed_since_trough <= min_reversion_sec
            ):
                denom = 1.0 - trough_price
                reversion_amount = (current_price - trough_price) / denom if denom > 0.0 else 0.0
                if reversion_amount >= reversion_pct and current_price > trough_price and current_price < 0.50:
                    if reversion_amount > best_reversion:
                        best_reversion = reversion_amount
                        chosen_direction = 1

            if best_reversion < 0.0:
                continue

            direction_up = chosen_direction == 1
            adjusted_entry = max(0.01, min(0.99, current_price if direction_up else 1.0 - current_price))
            entry_second = sec
            found = True
            break

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s4_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_prices: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lookback_window = int(combo[0])
    vol_threshold = combo[1]
    eval_second = int(combo[2])
    extreme_price_low = combo[3]
    extreme_price_high = combo[4]
    reversal_lookback = int(combo[5])
    reversal_min_move = combo[6]
    stop_loss = combo[7]
    take_profit = combo[8]

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        if int(total_seconds[market_idx]) <= eval_second:
            continue

        sec = eval_second
        start_sec = sec - lookback_window + 1
        if start_sec < 0:
            start_sec = 0

        values = np.empty(lookback_window + 1, dtype=np.float64)
        value_count = 0
        for pos in range(start_sec, sec + 1):
            value = prices[market_idx, pos]
            if np.isnan(value):
                continue
            values[value_count] = value
            value_count += 1

        if value_count < 8:
            continue

        if value_count < 3:
            continue
        diff_count = value_count - 1
        if diff_count < 2:
            continue
        diffs = np.empty(diff_count, dtype=np.float64)
        for idx in range(diff_count):
            diffs[idx] = values[idx + 1] - values[idx]
        mean = 0.0
        for idx in range(diff_count):
            mean += diffs[idx]
        mean /= diff_count
        variance = 0.0
        for idx in range(diff_count):
            delta = diffs[idx] - mean
            variance += delta * delta
        variance /= (diff_count - 1)
        vol = np.sqrt(variance)
        if vol < vol_threshold:
            continue

        price = nearest_prices[market_idx, sec]
        if np.isnan(price):
            continue

        recent_move = trailing_net_move_from_raw(prices, market_idx, sec, reversal_lookback)
        if np.isnan(recent_move):
            continue

        found = False
        direction_up = True
        adjusted_entry = 0.0
        if price <= extreme_price_low and recent_move >= reversal_min_move:
            direction_up = True
            adjusted_entry = max(0.01, min(0.99, price))
            found = True
        elif price >= extreme_price_high and recent_move <= -reversal_min_move:
            direction_up = False
            adjusted_entry = max(0.01, min(0.99, 1.0 - price))
            found = True

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, sec, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s5_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    hours: np.ndarray,
    nearest_prices: np.ndarray,
    allowed_hour_masks: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    entry_window_start = int(combo[0])
    entry_window_end = int(combo[1])
    allowed_hours_idx = int(combo[2])
    price_range_low = combo[3]
    price_range_high = combo[4]
    approach_lookback = int(combo[5])
    cross_buffer = combo[6]
    confirmation_lookback = int(combo[7])
    confirmation_min_move = combo[8]
    min_cross_move = combo[9]
    stop_loss = combo[10]
    take_profit = combo[11]

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        last_sec = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_sec < entry_window_start:
            continue

        current_hour = hours[market_idx]
        if allowed_hours_idx >= 0 and current_hour >= 0 and not allowed_hour_masks[allowed_hours_idx, current_hour]:
            continue

        found = False
        adjusted_entry = 0.0
        direction_up = True
        entry_second = -1

        for sec in range(entry_window_start, last_sec + 1):
            price = nearest_prices[market_idx, sec]
            prev_sec = sec - approach_lookback
            if prev_sec < 0:
                prev_price = np.nan
            else:
                prev_price = nearest_prices[market_idx, prev_sec]
            if np.isnan(price) or np.isnan(prev_price):
                continue
            if price < price_range_low or price > price_range_high:
                continue
            recent_move = trailing_net_move_from_raw(prices, market_idx, sec, confirmation_lookback)
            if np.isnan(recent_move):
                continue
            cross_move = price - prev_price

            if (
                prev_price <= 0.50 - cross_buffer
                and price >= 0.50 + cross_buffer
                and cross_move >= min_cross_move
                and recent_move >= confirmation_min_move
            ):
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, price))
                entry_second = sec
                found = True
                break
            if (
                prev_price >= 0.50 + cross_buffer
                and price <= 0.50 - cross_buffer
                and cross_move <= -min_cross_move
                and recent_move <= -confirmation_min_move
            ):
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - price))
                entry_second = sec
                found = True
                break

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s6_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    streak_directions: np.ndarray,
    streak_lengths: np.ndarray,
    nearest_prices: np.ndarray,
    combo: np.ndarray,
    entry_slippage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    streak_length_required = int(combo[0])
    streak_direction_filter = int(combo[1])
    entry_window_start = int(combo[2])
    entry_window_end = int(combo[3])
    price_floor = combo[4]
    price_ceiling = combo[5]
    stop_loss = combo[6]
    take_profit = combo[7]

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0

    for market_idx in range(market_count):
        streak_direction = streak_directions[market_idx]
        if streak_direction < 0:
            continue
        if int(streak_lengths[market_idx]) < streak_length_required:
            continue
        if streak_direction_filter != 2 and streak_direction != streak_direction_filter:
            continue

        last_sec = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_sec < entry_window_start:
            continue

        found = False
        adjusted_entry = 0.0
        direction_up = True
        entry_second = -1

        for sec in range(entry_window_start, last_sec + 1):
            up_price = nearest_prices[market_idx, sec]
            if np.isnan(up_price):
                continue
            if up_price < price_floor or up_price > price_ceiling:
                continue
            direction_up = streak_direction == 0
            adjusted_entry = max(0.01, min(0.99, up_price if direction_up else 1.0 - up_price))
            entry_second = sec
            found = True
            break

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


class _BaseWindowKernel:
    strategy_id = ""
    tolerance_values = np.array([2], dtype=np.int64)
    strategy_cls = None
    get_default_config = None

    def is_available(self) -> bool:
        return NUMBA_AVAILABLE

    def unavailable_reason(self) -> str:
        return NUMBA_IMPORT_ERROR or "Numba is not installed."

    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        common = build_common_payload(markets)
        nearest_prices = precompute_nearest_prices_multi(common.prices, common.total_seconds, self.tolerance_values)
        payload = WindowPayload(common=common, nearest_prices=nearest_prices)
        return PrecomputedDataset(
            strategy_id=strategy_id,
            markets=markets,
            payload=payload,
            eligible_markets=len(markets),
            skipped_markets_missing_features=0,
        )

    def materialize_trades(self, dataset: PrecomputedDataset, param_dict: dict[str, object], config_id: str) -> list[Trade]:
        base_config = self.get_default_config()
        config_fields = {field.name for field in dataclasses.fields(type(base_config))}
        strategy_params = {key: value for key, value in param_dict.items() if key in config_fields}
        exit_params = {key: value for key, value in param_dict.items() if key not in config_fields}
        strategy = self.strategy_cls(dataclasses.replace(base_config, **strategy_params))
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


class S2Accelerator(_BaseWindowKernel):
    strategy_id = "S2"
    tolerance_values = np.array([2, 3, 5], dtype=np.int64)
    strategy_cls = S2Strategy
    get_default_config = staticmethod(get_s2_default_config)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s2_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                payload.nearest_prices,
                self.tolerance_values,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S3Accelerator(_BaseWindowKernel):
    strategy_id = "S3"
    tolerance_values = np.array([2], dtype=np.int64)
    strategy_cls = S3Strategy
    get_default_config = staticmethod(get_s3_default_config)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        nearest = payload.nearest_prices[0]
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s3_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                nearest,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S4Accelerator(_BaseWindowKernel):
    strategy_id = "S4"
    tolerance_values = np.array([2], dtype=np.int64)
    strategy_cls = S4Strategy
    get_default_config = staticmethod(get_s4_default_config)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        nearest = payload.nearest_prices[0]
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s4_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                nearest,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S5Accelerator(_BaseWindowKernel):
    strategy_id = "S5"
    tolerance_values = np.array([2], dtype=np.int64)
    strategy_cls = S5Strategy
    get_default_config = staticmethod(get_s5_default_config)

    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        common = build_common_payload(markets)
        nearest_prices = precompute_nearest_prices_multi(common.prices, common.total_seconds, self.tolerance_values)
        encoded_hour_options = np.zeros((len(param_grid["allowed_hours"]), 24), dtype=np.bool_)
        self._hour_option_lookup = {}
        for idx, value in enumerate(param_grid["allowed_hours"]):
            self._hour_option_lookup[self._hour_key(value)] = idx
            if value is None:
                encoded_hour_options[idx, :] = True
            else:
                for hour in value:
                    encoded_hour_options[idx, int(hour)] = True
        payload = S5Payload(common=common, nearest_prices=nearest_prices[0], encoded_hour_options=encoded_hour_options)
        return PrecomputedDataset(strategy_id=strategy_id, markets=markets, payload=payload, eligible_markets=len(markets), skipped_markets_missing_features=0)

    @staticmethod
    def _hour_key(allowed_hours: list[int] | None) -> tuple[int, ...] | None:
        return None if allowed_hours is None else tuple(int(hour) for hour in allowed_hours)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        allowed_hours = combo[2]
        hours_code = self._hour_option_lookup[self._hour_key(allowed_hours)]
        values = list(combo)
        values[2] = float(hours_code)
        return np.array(values, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: S5Payload = dataset.payload
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s5_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                payload.common.hours,
                payload.nearest_prices,
                payload.encoded_hour_options,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S6Accelerator(_BaseWindowKernel):
    strategy_id = "S6"
    tolerance_values = np.array([2], dtype=np.int64)
    strategy_cls = S6Strategy
    get_default_config = staticmethod(get_s6_default_config)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        filter_value = combo[1]
        if filter_value == "Down":
            encoded_filter = 0.0
        elif filter_value == "Up":
            encoded_filter = 1.0
        else:
            encoded_filter = 2.0
        values = list(combo)
        values[1] = encoded_filter
        return np.array(values, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        nearest = payload.nearest_prices[0]
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s6_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                payload.common.streak_directions,
                payload.common.streak_lengths,
                nearest,
                combo_array,
                dataset.slippage,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results
