"""Accelerated optimization kernels for strategies S7 through S12."""

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
)
from analysis.accelerators.s2_s6 import (
    WindowPayload,
    _evaluate_s2_combo,
    _evaluate_s4_combo,
    _get_tolerance_index,
)
from analysis.backtest.engine import Trade
from analysis.backtest_strategies import run_strategy
from shared.strategies.S7.config import get_default_config as get_s7_default_config
from shared.strategies.S7.strategy import S7Strategy
from shared.strategies.S8.config import get_default_config as get_s8_default_config
from shared.strategies.S8.strategy import S8Strategy
from shared.strategies.S9.config import get_default_config as get_s9_default_config
from shared.strategies.S9.strategy import S9Strategy
from shared.strategies.S10.config import get_default_config as get_s10_default_config
from shared.strategies.S10.strategy import S10Strategy
from shared.strategies.S11.config import get_default_config as get_s11_default_config
from shared.strategies.S11.strategy import S11Strategy
from shared.strategies.S12.config import get_default_config as get_s12_default_config
from shared.strategies.S12.strategy import S12Strategy


@dataclass
class S7Payload:
    common: object
    s1_nearest: np.ndarray
    s1_trailing: np.ndarray
    s1_lookbacks: np.ndarray
    s2_nearest: np.ndarray
    s2_tolerances: np.ndarray
    s4_nearest: np.ndarray


@njit(cache=True)
def _compute_s1_detection(
    prices: np.ndarray,
    nearest_prices: np.ndarray,
    trailing_moves: np.ndarray,
    lookbacks: np.ndarray,
    market_idx: int,
    sec: int,
    entry_window_start: int,
    entry_window_end: int,
    price_low_threshold: float,
    price_high_threshold: float,
    min_deviation: float,
    rebound_lookback: int,
    rebound_min_move: float,
) -> int:
    if sec < entry_window_start or sec > entry_window_end:
        return -1

    price = nearest_prices[market_idx, sec]
    if np.isnan(price):
        return -1

    lookback_idx = -1
    for idx in range(lookbacks.shape[0]):
        if int(lookbacks[idx]) == rebound_lookback:
            lookback_idx = idx
            break
    if lookback_idx < 0:
        return -1

    recent_move = trailing_moves[lookback_idx, market_idx, sec]
    if np.isnan(recent_move):
        return -1

    if price <= price_low_threshold and (0.50 - price) >= min_deviation and recent_move >= rebound_min_move:
        return 1
    if price >= price_high_threshold and (price - 0.50) >= min_deviation and recent_move <= -rebound_min_move:
        return 0
    return -1


@njit(cache=True)
def _compute_s2_detection(
    prices: np.ndarray,
    nearest_prices: np.ndarray,
    tolerances: np.ndarray,
    market_idx: int,
    sec: int,
    eval_window_start: int,
    eval_window_end: int,
    momentum_threshold: float,
    tolerance: int,
    max_entry_second: int,
    efficiency_min: float,
    min_distance_from_mid: float,
) -> int:
    if sec < eval_window_end or sec > max_entry_second:
        return -1

    tol_idx = _get_tolerance_index(tolerances, tolerance)
    lookback = max(1, eval_window_end - eval_window_start)
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
        return -1
    net_move = last_value - first_value
    if abs(net_move) < momentum_threshold:
        return -1
    efficiency = abs(net_move) / path_length if path_length > 1e-9 else 0.0
    if efficiency < efficiency_min:
        return -1

    price = nearest_prices[tol_idx, market_idx, sec]
    if np.isnan(price) or abs(price - 0.50) < min_distance_from_mid:
        return -1
    return 1 if net_move > 0 else 0


@njit(cache=True)
def _compute_s4_detection(
    prices: np.ndarray,
    nearest_prices: np.ndarray,
    market_total_seconds: int,
    market_idx: int,
    sec: int,
    lookback_window: int,
    vol_threshold: float,
    eval_second: int,
    extreme_price_low: float,
    extreme_price_high: float,
    reversal_lookback: int,
    reversal_min_move: float,
) -> int:
    if sec < eval_second or sec != eval_second or market_total_seconds <= eval_second:
        return -1

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
        return -1

    diff_count = value_count - 1
    if diff_count < 2:
        return -1
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
        return -1

    price = nearest_prices[market_idx, sec]
    if np.isnan(price):
        return -1

    start_rev = sec - reversal_lookback + 1
    if start_rev < 0:
        start_rev = 0
    first_val = np.nan
    last_val = np.nan
    valid_count = 0
    for pos in range(start_rev, sec + 1):
        value = prices[market_idx, pos]
        if np.isnan(value):
            continue
        if valid_count == 0:
            first_val = value
        last_val = value
        valid_count += 1
    if valid_count < 2:
        return -1
    recent_move = last_val - first_val

    if price <= extreme_price_low and recent_move >= reversal_min_move:
        return 1
    if price >= extreme_price_high and recent_move <= -reversal_min_move:
        return 0
    return -1


@njit(cache=True)
def _evaluate_s7_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    s1_nearest: np.ndarray,
    s1_trailing: np.ndarray,
    s1_lookbacks: np.ndarray,
    s2_nearest: np.ndarray,
    s2_tolerances: np.ndarray,
    s4_nearest: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    min_agreement = int(combo[0])
    calibration_enabled = int(combo[1]) == 1
    momentum_enabled = int(combo[2]) == 1
    volatility_enabled = int(combo[3]) == 1
    calibration_min_deviation = combo[4]
    calibration_rebound_min_move = combo[5]
    momentum_threshold = combo[6]
    momentum_efficiency_min = combo[7]
    volatility_threshold = combo[8]
    volatility_reversal_min_move = combo[9]
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
        market_total_seconds = int(total_seconds[market_idx])
        found = False
        entry_second = -1
        direction_up = True
        adjusted_entry = 0.0

        for sec in range(market_total_seconds):
            up_votes = 0
            down_votes = 0

            if calibration_enabled:
                detection = _compute_s1_detection(
                    prices, s1_nearest, s1_trailing, s1_lookbacks, market_idx, sec,
                    30, 120, 0.42, 0.58, calibration_min_deviation, 8, calibration_rebound_min_move,
                )
                if detection == 1:
                    up_votes += 1
                elif detection == 0:
                    down_votes += 1

            if momentum_enabled:
                detection = _compute_s2_detection(
                    prices, s2_nearest, s2_tolerances, market_idx, sec,
                    30, 60, momentum_threshold, 3, 150, momentum_efficiency_min, 0.04,
                )
                if detection == 1:
                    up_votes += 1
                elif detection == 0:
                    down_votes += 1

            if volatility_enabled:
                detection = _compute_s4_detection(
                    prices, s4_nearest, market_total_seconds, market_idx, sec,
                    60, volatility_threshold, 45, 0.30, 0.70, 6, volatility_reversal_min_move,
                )
                if detection == 1:
                    up_votes += 1
                elif detection == 0:
                    down_votes += 1

            if up_votes >= min_agreement:
                price = s1_nearest[market_idx, sec]
                if np.isnan(price):
                    continue
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, price))
                entry_second = sec
                found = True
                break
            if down_votes >= min_agreement:
                price = s1_nearest[market_idx, sec]
                if np.isnan(price):
                    continue
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - price))
                entry_second = sec
                found = True
                break

        if not found:
            continue

        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1

    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s8_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_tol1: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    setup_window_end = int(combo[0])
    breakout_scan_start = int(combo[1])
    breakout_scan_end = int(combo[2])
    breakout_buffer = combo[3]
    min_range_width = combo[4]
    max_range_width = combo[5]
    confirmation_points = int(combo[6])
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
        market_total_seconds = int(total_seconds[market_idx])
        scan_start = breakout_scan_start
        if setup_window_end + 1 > scan_start:
            scan_start = setup_window_end + 1
        if scan_start >= market_total_seconds:
            continue
        last_scan = min(breakout_scan_end, market_total_seconds - 1)
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1

        for sec in range(scan_start, last_scan + 1):
            setup_end = setup_window_end if setup_window_end < sec else sec - 1
            if setup_end < 0:
                continue
            setup_vals = np.empty(setup_end + 1, dtype=np.float64)
            count = 0
            for pos in range(0, setup_end + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                setup_vals[count] = value
                count += 1
            if count < 6:
                continue
            range_high = setup_vals[0]
            range_low = setup_vals[0]
            for idx in range(1, count):
                value = setup_vals[idx]
                if value > range_high:
                    range_high = value
                if value < range_low:
                    range_low = value
            range_width = range_high - range_low
            if range_width < min_range_width or range_width > max_range_width:
                continue

            price = nearest_tol1[market_idx, sec]
            if np.isnan(price) or abs(price - 0.50) < min_distance_from_mid:
                continue
            up_threshold = range_high + breakout_buffer
            down_threshold = range_low - breakout_buffer

            if price >= up_threshold:
                confirm_start = sec - confirmation_points + 1
                ok = True
                for confirm_sec in range(confirm_start, sec + 1):
                    if confirm_sec < 0:
                        ok = False
                        break
                    value = nearest_tol1[market_idx, confirm_sec]
                    if np.isnan(value) or value < up_threshold:
                        ok = False
                        break
                if ok:
                    direction_up = True
                    adjusted_entry = max(0.01, min(0.99, price))
                    entry_second = sec
                    found = True
                    break

            if price <= down_threshold:
                confirm_start = sec - confirmation_points + 1
                ok = True
                for confirm_sec in range(confirm_start, sec + 1):
                    if confirm_sec < 0:
                        ok = False
                        break
                    value = nearest_tol1[market_idx, confirm_sec]
                    if np.isnan(value) or value > down_threshold:
                        ok = False
                        break
                if ok:
                    direction_up = False
                    adjusted_entry = max(0.01, min(0.99, 1.0 - price))
                    entry_second = sec
                    found = True
                    break

        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _path_efficiency(values: np.ndarray, count: int) -> float:
    if count < 2:
        return 0.0
    path_length = 0.0
    for idx in range(1, count):
        path_length += abs(values[idx] - values[idx - 1])
    if path_length <= 1e-9:
        return 0.0
    net_move = values[count - 1] - values[0]
    return abs(net_move) / path_length


@njit(cache=True)
def _direction_flips(values: np.ndarray, count: int, noise_threshold: float = 0.002) -> int:
    if count < 3:
        return 0
    last_sign = 0
    flips = 0
    for idx in range(1, count):
        delta = values[idx] - values[idx - 1]
        if abs(delta) <= noise_threshold:
            continue
        sign = 1 if delta > 0 else -1
        if last_sign != 0 and sign != last_sign:
            flips += 1
        last_sign = sign
    return flips


@njit(cache=True)
def _evaluate_s9_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_tol1: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    compression_window = int(combo[0])
    compression_max_std = combo[1]
    compression_max_range = combo[2]
    trigger_scan_start = int(combo[3])
    trigger_scan_end = int(combo[4])
    breakout_distance = combo[5]
    momentum_lookback = int(combo[6])
    efficiency_min = combo[7]
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
        market_total_seconds = int(total_seconds[market_idx])
        start_scan = trigger_scan_start
        if compression_window + 1 > start_scan:
            start_scan = compression_window + 1
        if momentum_lookback > start_scan:
            start_scan = momentum_lookback
        if start_scan >= market_total_seconds:
            continue
        last_scan = min(trigger_scan_end, market_total_seconds - 1)
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1

        for sec in range(start_scan, last_scan + 1):
            comp_end = compression_window if compression_window < sec else sec - 1
            comp_vals = np.empty(comp_end + 1, dtype=np.float64)
            comp_count = 0
            for pos in range(0, comp_end + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                comp_vals[comp_count] = value
                comp_count += 1
            if comp_count < 8:
                continue
            comp_high = comp_vals[0]
            comp_low = comp_vals[0]
            mean = 0.0
            for idx in range(comp_count):
                value = comp_vals[idx]
                mean += value
                if value > comp_high:
                    comp_high = value
                if value < comp_low:
                    comp_low = value
            mean /= comp_count
            variance = 0.0
            for idx in range(comp_count):
                delta = comp_vals[idx] - mean
                variance += delta * delta
            variance /= comp_count
            compression_std = np.sqrt(variance)
            compression_range = comp_high - comp_low
            if compression_std > compression_max_std or compression_range > compression_max_range:
                continue

            price = nearest_tol1[market_idx, sec]
            if np.isnan(price):
                continue
            start_m = sec - momentum_lookback
            if start_m < 0:
                start_m = 0
            m_vals = np.empty(momentum_lookback + 1, dtype=np.float64)
            m_count = 0
            for pos in range(start_m, sec + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                m_vals[m_count] = value
                m_count += 1
            if m_count < 4:
                continue
            recent_net_move = m_vals[m_count - 1] - m_vals[0]
            recent_efficiency = _path_efficiency(m_vals, m_count)
            if recent_efficiency < efficiency_min:
                continue

            if price >= comp_high + breakout_distance and recent_net_move >= breakout_distance:
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, price))
                entry_second = sec
                found = True
                break
            if price <= comp_low - breakout_distance and recent_net_move <= -breakout_distance:
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - price))
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s10_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    impulse_start = int(combo[0])
    impulse_end = int(combo[1])
    impulse_threshold = combo[2]
    retrace_window = int(combo[3])
    retrace_min = combo[4]
    retrace_max = combo[5]
    reacceleration_threshold = combo[6]
    impulse_efficiency_min = combo[7]
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
        market_total_seconds = int(total_seconds[market_idx])
        if market_total_seconds <= impulse_end:
            continue
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(impulse_end + 1, market_total_seconds):
            end_idx = impulse_end if impulse_end < sec else sec - 1
            if end_idx < impulse_start:
                continue
            impulse_vals = np.empty(end_idx - impulse_start + 1, dtype=np.float64)
            impulse_secs = np.empty(end_idx - impulse_start + 1, dtype=np.int64)
            count = 0
            for pos in range(impulse_start, end_idx + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                impulse_vals[count] = value
                impulse_secs[count] = pos
                count += 1
            if count < 6:
                continue
            eff = _path_efficiency(impulse_vals, count)
            if eff < impulse_efficiency_min:
                continue
            start_price = impulse_vals[0]
            end_price = impulse_vals[count - 1]
            net_move = end_price - start_price
            if abs(net_move) < impulse_threshold:
                continue
            if net_move > 0:
                peak_price = impulse_vals[0]
                peak_sec = impulse_secs[0]
                for idx in range(1, count):
                    if impulse_vals[idx] > peak_price:
                        peak_price = impulse_vals[idx]
                        peak_sec = impulse_secs[idx]
                if sec <= peak_sec or sec > peak_sec + retrace_window:
                    continue
                impulse_size = peak_price - start_price
                if impulse_size <= 0:
                    continue
                pullback_vals = np.empty(sec - peak_sec, dtype=np.float64)
                pull_count = 0
                for pos in range(peak_sec + 1, sec + 1):
                    value = prices[market_idx, pos]
                    if np.isnan(value):
                        continue
                    pullback_vals[pull_count] = value
                    pull_count += 1
                if pull_count < 2:
                    continue
                pullback_low = pullback_vals[0]
                for idx in range(1, pull_count):
                    if pullback_vals[idx] < pullback_low:
                        pullback_low = pullback_vals[idx]
                current_price = pullback_vals[pull_count - 1]
                retrace_fraction = (peak_price - pullback_low) / impulse_size
                if retrace_fraction < retrace_min or retrace_fraction > retrace_max:
                    continue
                if current_price - pullback_low < reacceleration_threshold:
                    continue
                if current_price <= start_price:
                    continue
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, current_price))
                entry_second = sec
                found = True
                break
            else:
                trough_price = impulse_vals[0]
                trough_sec = impulse_secs[0]
                for idx in range(1, count):
                    if impulse_vals[idx] < trough_price:
                        trough_price = impulse_vals[idx]
                        trough_sec = impulse_secs[idx]
                if sec <= trough_sec or sec > trough_sec + retrace_window:
                    continue
                impulse_size = start_price - trough_price
                if impulse_size <= 0:
                    continue
                pullback_vals = np.empty(sec - trough_sec, dtype=np.float64)
                pull_count = 0
                for pos in range(trough_sec + 1, sec + 1):
                    value = prices[market_idx, pos]
                    if np.isnan(value):
                        continue
                    pullback_vals[pull_count] = value
                    pull_count += 1
                if pull_count < 2:
                    continue
                pullback_high = pullback_vals[0]
                for idx in range(1, pull_count):
                    if pullback_vals[idx] > pullback_high:
                        pullback_high = pullback_vals[idx]
                current_price = pullback_vals[pull_count - 1]
                retrace_fraction = (pullback_high - trough_price) / impulse_size
                if retrace_fraction < retrace_min or retrace_fraction > retrace_max:
                    continue
                if pullback_high - current_price < reacceleration_threshold:
                    continue
                if current_price >= start_price:
                    continue
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - current_price))
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s11_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    nearest_tol1: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    precondition_window = int(combo[0])
    extreme_deviation = combo[1]
    reclaim_scan_start = int(combo[2])
    reclaim_scan_end = int(combo[3])
    hold_seconds = int(combo[4])
    hold_buffer = combo[5]
    post_reclaim_move = combo[6]
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
        market_total_seconds = int(total_seconds[market_idx])
        if reclaim_scan_start >= market_total_seconds:
            continue
        last_scan = min(reclaim_scan_end, market_total_seconds - 1)
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(reclaim_scan_start, last_scan + 1):
            hold_start = sec - hold_seconds + 1
            if hold_start <= 0:
                continue
            pre_start = hold_start - precondition_window
            if pre_start < 0:
                pre_start = 0
            had_downside_extreme = False
            had_upside_extreme = False
            valid_count = 0
            for pos in range(pre_start, hold_start):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                valid_count += 1
                if value <= 0.50 - extreme_deviation:
                    had_downside_extreme = True
                if value >= 0.50 + extreme_deviation:
                    had_upside_extreme = True
            if valid_count < 4:
                continue
            hold_prices = np.empty(hold_seconds, dtype=np.float64)
            ok = True
            hp_count = 0
            for pos in range(hold_start, sec + 1):
                value = nearest_tol1[market_idx, pos]
                if np.isnan(value):
                    ok = False
                    break
                hold_prices[hp_count] = value
                hp_count += 1
            if not ok:
                continue
            confirm_price = hold_prices[hp_count - 1]
            all_up = True
            all_down = True
            for idx in range(hp_count):
                if hold_prices[idx] < 0.50 + hold_buffer:
                    all_up = False
                if hold_prices[idx] > 0.50 - hold_buffer:
                    all_down = False
            if had_downside_extreme and all_up and confirm_price >= 0.50 + hold_buffer + post_reclaim_move:
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, confirm_price))
                entry_second = sec
                found = True
                break
            if had_upside_extreme and all_down and confirm_price <= 0.50 - hold_buffer - post_reclaim_move:
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - confirm_price))
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


@njit(cache=True)
def _evaluate_s12_combo(
    prices: np.ndarray,
    total_seconds: np.ndarray,
    final_outcomes: np.ndarray,
    asset_codes: np.ndarray,
    duration_minutes: np.ndarray,
    fee_active: np.ndarray,
    combo: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    late_phase_start_pct = combo[0]
    lookback_seconds = int(combo[1])
    net_move_threshold = combo[2]
    efficiency_min = combo[3]
    max_flip_count = int(combo[4])
    min_price_distance_from_mid = combo[5]
    min_remaining_seconds = int(combo[6])
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
        market_total_seconds = int(total_seconds[market_idx])
        phase_start = int(market_total_seconds * late_phase_start_pct)
        start_scan = phase_start if phase_start > lookback_seconds else lookback_seconds
        end_scan = market_total_seconds - min_remaining_seconds - 1
        if start_scan > end_scan:
            continue
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(start_scan, end_scan + 1):
            start_sec = sec - lookback_seconds
            if start_sec < 0:
                start_sec = 0
            vals = np.empty(lookback_seconds + 1, dtype=np.float64)
            count = 0
            for pos in range(start_sec, sec + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                vals[count] = value
                count += 1
            if count < 6:
                continue
            current_price = vals[count - 1]
            net_move = vals[count - 1] - vals[0]
            if abs(net_move) < net_move_threshold:
                continue
            if abs(current_price - 0.50) < min_price_distance_from_mid:
                continue
            efficiency = _path_efficiency(vals, count)
            if efficiency < efficiency_min:
                continue
            flips = _direction_flips(vals, count, 0.002)
            if flips > max_flip_count:
                continue
            if net_move > 0 and current_price > 0.50:
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, current_price))
                entry_second = sec
                found = True
                break
            if net_move < 0 and current_price < 0.50:
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - current_price))
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices, total_seconds, final_outcomes, fee_active,
            market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit,
        )
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count]


class _BaseKernel:
    strategy_id = ""
    tolerance_values = np.array([1], dtype=np.int64)
    strategy_cls = None
    get_default_config = None

    def is_available(self) -> bool:
        return NUMBA_AVAILABLE

    def unavailable_reason(self) -> str:
        return NUMBA_IMPORT_ERROR or "Numba is not installed."

    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        common = build_common_payload(markets)
        nearest = precompute_nearest_prices_multi(common.prices, common.total_seconds, self.tolerance_values)
        payload = WindowPayload(common=common, nearest_prices=nearest)
        return PrecomputedDataset(strategy_id=strategy_id, markets=markets, payload=payload, eligible_markets=len(markets), skipped_markets_missing_features=0)

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
            stop_loss=exit_params.get("stop_loss"),
            take_profit=exit_params.get("take_profit"),
            log_summary=False,
        )
        return trades


class S7Accelerator(_BaseKernel):
    strategy_id = "S7"
    strategy_cls = S7Strategy
    get_default_config = staticmethod(get_s7_default_config)
    tolerance_values = np.array([1], dtype=np.int64)

    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        common = build_common_payload(markets)
        s1_lookbacks = np.array([8], dtype=np.int64)
        s1_nearest = precompute_nearest_prices_multi(common.prices, common.total_seconds, np.array([2], dtype=np.int64))[0]
        from analysis.accelerators.s1 import _precompute_trailing_moves
        s1_trailing = _precompute_trailing_moves(common.prices, common.total_seconds, s1_lookbacks)
        s2_tolerances = np.array([3], dtype=np.int64)
        s2_nearest = precompute_nearest_prices_multi(common.prices, common.total_seconds, s2_tolerances)
        s4_nearest = s1_nearest
        payload = S7Payload(common, s1_nearest, s1_trailing, s1_lookbacks, s2_nearest, s2_tolerances, s4_nearest)
        return PrecomputedDataset(strategy_id=strategy_id, markets=markets, payload=payload, eligible_markets=len(markets), skipped_markets_missing_features=0)

    def encode_combo(self, combo: tuple[object, ...]) -> np.ndarray:
        encoded = [
            combo[0],
            1.0 if combo[1] else 0.0,
            1.0 if combo[2] else 0.0,
            1.0 if combo[3] else 0.0,
            combo[4],
            combo[5],
            combo[6],
            combo[7],
            combo[8],
            combo[9],
            combo[10],
            combo[11],
        ]
        return np.array(encoded, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: S7Payload = dataset.payload
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s7_combo(
                payload.common.prices,
                payload.common.total_seconds,
                payload.common.final_outcomes,
                payload.common.asset_codes,
                payload.common.duration_minutes,
                payload.common.fee_active,
                payload.s1_nearest,
                payload.s1_trailing,
                payload.s1_lookbacks,
                payload.s2_nearest,
                payload.s2_tolerances,
                payload.s4_nearest,
                combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S8Accelerator(_BaseKernel):
    strategy_id = "S8"
    strategy_cls = S8Strategy
    get_default_config = staticmethod(get_s8_default_config)
    tolerance_values = np.array([1], dtype=np.int64)

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        nearest = payload.nearest_prices[0]
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s8_combo(
                payload.common.prices, payload.common.total_seconds, payload.common.final_outcomes,
                payload.common.asset_codes, payload.common.duration_minutes, payload.common.fee_active,
                nearest, combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S9Accelerator(_BaseKernel):
    strategy_id = "S9"
    strategy_cls = S9Strategy
    get_default_config = staticmethod(get_s9_default_config)
    tolerance_values = np.array([1], dtype=np.int64)

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        nearest = payload.nearest_prices[0]
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s9_combo(
                payload.common.prices, payload.common.total_seconds, payload.common.final_outcomes,
                payload.common.asset_codes, payload.common.duration_minutes, payload.common.fee_active,
                nearest, combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S10Accelerator(_BaseKernel):
    strategy_id = "S10"
    strategy_cls = S10Strategy
    get_default_config = staticmethod(get_s10_default_config)

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s10_combo(
                payload.common.prices, payload.common.total_seconds, payload.common.final_outcomes,
                payload.common.asset_codes, payload.common.duration_minutes, payload.common.fee_active,
                combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S11Accelerator(_BaseKernel):
    strategy_id = "S11"
    strategy_cls = S11Strategy
    get_default_config = staticmethod(get_s11_default_config)
    tolerance_values = np.array([1], dtype=np.int64)

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        nearest = payload.nearest_prices[0]
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s11_combo(
                payload.common.prices, payload.common.total_seconds, payload.common.final_outcomes,
                payload.common.asset_codes, payload.common.duration_minutes, payload.common.fee_active,
                nearest, combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results


class S12Accelerator(_BaseKernel):
    strategy_id = "S12"
    strategy_cls = S12Strategy
    get_default_config = staticmethod(get_s12_default_config)

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        payload: WindowPayload = dataset.payload
        results = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            pnls, entry_fees, exit_fees, asset_codes, durations = _evaluate_s12_combo(
                payload.common.prices, payload.common.total_seconds, payload.common.final_outcomes,
                payload.common.asset_codes, payload.common.duration_minutes, payload.common.fee_active,
                combo_array,
            )
            metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
            metrics["eligible_markets"] = dataset.eligible_markets
            metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features
            metrics.update(param_dict)
            results.append(metrics)
        return results
