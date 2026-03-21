"""Accelerated optimization kernels for strategies S13 through S19."""

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
from analysis.backtest.engine import Trade
from analysis.backtest_strategies import run_strategy
from shared.strategies.S13.config import get_default_config as get_s13_default_config
from shared.strategies.S13.strategy import S13Strategy
from shared.strategies.S14.config import get_default_config as get_s14_default_config
from shared.strategies.S14.strategy import S14Strategy
from shared.strategies.S15.config import get_default_config as get_s15_default_config
from shared.strategies.S15.strategy import S15Strategy
from shared.strategies.S16.config import get_default_config as get_s16_default_config
from shared.strategies.S16.strategy import S16Strategy
from shared.strategies.S17.config import get_default_config as get_s17_default_config
from shared.strategies.S17.strategy import S17Strategy
from shared.strategies.S18.config import get_default_config as get_s18_default_config
from shared.strategies.S18.strategy import S18Strategy
from shared.strategies.S19.config import get_default_config as get_s19_default_config
from shared.strategies.S19.strategy import S19Strategy


FEATURE_COLUMNS = (
    "underlying_return_5s",
    "underlying_return_10s",
    "underlying_return_30s",
    "market_up_delta_5s",
    "market_up_delta_10s",
    "market_up_delta_30s",
    "underlying_realized_vol_10s",
    "underlying_realized_vol_30s",
    "direction_mismatch_5s",
    "direction_mismatch_10s",
    "direction_mismatch_30s",
    "underlying_trade_count",
    "underlying_volume",
    "underlying_taker_buy_base_volume",
    "market_up_delta_from_market_open",
    "underlying_return_from_market_open",
)


@dataclass
class FeaturePayload:
    common: object
    nearest_tol1: np.ndarray
    matrices: dict[str, np.ndarray]
    availability: dict[str, np.ndarray]


@dataclass
class S13Payload:
    common: object
    nearest_tol1: np.ndarray
    ret5: np.ndarray
    ret10: np.ndarray
    ret30: np.ndarray
    m5: np.ndarray
    m10: np.ndarray
    m30: np.ndarray
    vol10: np.ndarray
    vol30: np.ndarray
    avail_ret5: np.ndarray
    avail_ret10: np.ndarray
    avail_ret30: np.ndarray
    avail_m5: np.ndarray
    avail_m10: np.ndarray
    avail_m30: np.ndarray
    avail_v10: np.ndarray
    avail_v30: np.ndarray


def _build_feature_payload(markets: list[dict], columns: tuple[str, ...] = FEATURE_COLUMNS) -> FeaturePayload:
    common = build_common_payload(markets)
    nearest_tol1 = precompute_nearest_prices_multi(common.prices, common.total_seconds, np.array([1], dtype=np.int64))[0]

    matrices: dict[str, np.ndarray] = {}
    availability: dict[str, np.ndarray] = {}
    max_seconds = common.prices.shape[1]
    for column in columns:
        matrix = np.full((len(markets), max_seconds), np.nan, dtype=np.float64)
        available = np.zeros(len(markets), dtype=np.bool_)
        for idx, market in enumerate(markets):
            series = market.get("feature_series", {}).get(column)
            if series is None:
                continue
            values = np.asarray(series, dtype=np.float64)
            matrix[idx, : values.shape[0]] = values
            available[idx] = bool(np.any(np.isfinite(values)))
        matrices[column] = matrix
        availability[column] = available

    return FeaturePayload(common=common, nearest_tol1=nearest_tol1, matrices=matrices, availability=availability)


def _build_s13_payload(markets: list[dict]) -> S13Payload:
    columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "market_up_delta_5s",
        "market_up_delta_10s",
        "market_up_delta_30s",
        "underlying_realized_vol_10s",
        "underlying_realized_vol_30s",
    )
    payload = _build_feature_payload(markets, columns)
    return S13Payload(
        common=payload.common,
        nearest_tol1=payload.nearest_tol1,
        ret5=payload.matrices["underlying_return_5s"],
        ret10=payload.matrices["underlying_return_10s"],
        ret30=payload.matrices["underlying_return_30s"],
        m5=payload.matrices["market_up_delta_5s"],
        m10=payload.matrices["market_up_delta_10s"],
        m30=payload.matrices["market_up_delta_30s"],
        vol10=payload.matrices["underlying_realized_vol_10s"],
        vol30=payload.matrices["underlying_realized_vol_30s"],
        avail_ret5=payload.availability["underlying_return_5s"],
        avail_ret10=payload.availability["underlying_return_10s"],
        avail_ret30=payload.availability["underlying_return_30s"],
        avail_m5=payload.availability["market_up_delta_5s"],
        avail_m10=payload.availability["market_up_delta_10s"],
        avail_m30=payload.availability["market_up_delta_30s"],
        avail_v10=payload.availability["underlying_realized_vol_10s"],
        avail_v30=payload.availability["underlying_realized_vol_30s"],
    )


@njit(cache=True)
def _valid_feature_market(availability: np.ndarray, market_idx: int) -> bool:
    return availability[market_idx]


@njit(cache=True)
def _evaluate_s13_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1,
    ret5, ret10, ret30, m5, m10, m30, vol10, vol30,
    avail_ret5, avail_ret10, avail_ret30, avail_m5, avail_m10, avail_m30, avail_v10, avail_v30,
    combo,
    entry_slippage,
):
    feature_window = int(combo[0])
    entry_window_start = int(combo[1])
    entry_window_end = int(combo[2])
    min_underlying_return = combo[3]
    min_market_confirmation = combo[4]
    max_market_delta = combo[5]
    max_price_distance_from_mid = combo[6]
    max_underlying_vol = combo[7]
    stop_loss = combo[8]
    take_profit = combo[9]

    if feature_window == 5:
        ret = ret5; mdelta = m5; vol = vol10
        avail_a = avail_ret5; avail_b = avail_m5; avail_c = avail_v10
    elif feature_window == 10:
        ret = ret10; mdelta = m10; vol = vol30
        avail_a = avail_ret10; avail_b = avail_m10; avail_c = avail_v30
    else:
        ret = ret30; mdelta = m30; vol = vol30
        avail_a = avail_ret30; avail_b = avail_m30; avail_c = avail_v30

    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64)
    entry_fees = np.empty(market_count, dtype=np.float64)
    exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64)
    trade_durations = np.empty(market_count, dtype=np.int64)
    trade_market_indices = np.empty(market_count, dtype=np.int64)
    trade_count = 0
    eligible_markets = 0

    for market_idx in range(market_count):
        if not (avail_a[market_idx] and avail_b[market_idx] and avail_c[market_idx]):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]
            underlying_return = ret[market_idx, sec]
            market_delta = mdelta[market_idx, sec]
            underlying_vol = vol[market_idx, sec]
            if np.isnan(up_price) or np.isnan(underlying_return) or np.isnan(market_delta) or np.isnan(underlying_vol):
                continue
            if underlying_vol > max_underlying_vol:
                continue
            if abs(up_price - 0.50) > max_price_distance_from_mid:
                continue
            if underlying_return >= min_underlying_return and min_market_confirmation <= market_delta <= max_market_delta and up_price > 0.50:
                direction_up = True
                adjusted_entry = max(0.01, min(0.99, up_price))
                entry_second = sec
                found = True
                break
            if underlying_return <= -min_underlying_return and -max_market_delta <= market_delta <= -min_market_confirmation and up_price < 0.50:
                direction_up = False
                adjusted_entry = max(0.01, min(0.99, 1.0 - up_price))
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl
        entry_fees[trade_count] = entry_fee
        exit_fees[trade_count] = exit_fee
        trade_asset_codes[trade_count] = asset_codes[market_idx]
        trade_durations[trade_count] = duration_minutes[market_idx]
        trade_market_indices[trade_count] = market_idx
        trade_count += 1
    return (
        pnls[:trade_count],
        entry_fees[:trade_count],
        exit_fees[:trade_count],
        trade_asset_codes[:trade_count],
        trade_durations[:trade_count],
        trade_market_indices[:trade_count],
        eligible_markets,
    )


@njit(cache=True)
def _evaluate_s14_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1,
    ret5, ret10, ret30, m5, m10, m30, mm5, mm10, mm30,
    avail_ret5, avail_ret10, avail_ret30, avail_m5, avail_m10, avail_m30, avail_mm5, avail_mm10, avail_mm30,
    combo,
    entry_slippage,
):
    feature_window = int(combo[0]); entry_window_start = int(combo[1]); entry_window_end = int(combo[2])
    min_market_delta_abs = combo[3]; max_underlying_return_abs = combo[4]; extreme_price_low = combo[5]; extreme_price_high = combo[6]
    require_direction_mismatch = int(combo[7]) == 1; stop_loss = combo[8]; take_profit = combo[9]
    if feature_window == 5:
        ret = ret5; mdelta = m5; mismatch = mm5; avail_a = avail_ret5; avail_b = avail_m5; avail_m = avail_mm5
    elif feature_window == 10:
        ret = ret10; mdelta = m10; mismatch = mm10; avail_a = avail_ret10; avail_b = avail_m10; avail_m = avail_mm10
    else:
        ret = ret30; mdelta = m30; mismatch = mm30; avail_a = avail_ret30; avail_b = avail_m30; avail_m = avail_mm30
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_market_indices = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_a[market_idx] and avail_b[market_idx] and ((not require_direction_mismatch) or avail_m[market_idx])):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]; underlying_return = ret[market_idx, sec]; market_delta = mdelta[market_idx, sec]; mismatch_v = mismatch[market_idx, sec]
            if np.isnan(up_price) or np.isnan(underlying_return) or np.isnan(market_delta):
                continue
            mismatch_ok = True
            if require_direction_mismatch:
                mismatch_ok = (not np.isnan(mismatch_v)) and mismatch_v >= 0.5
            if market_delta >= min_market_delta_abs and abs(underlying_return) <= max_underlying_return_abs and up_price >= extreme_price_high and mismatch_ok:
                direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
            if market_delta <= -min_market_delta_abs and abs(underlying_return) <= max_underlying_return_abs and up_price <= extreme_price_low and mismatch_ok:
                direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_market_indices[trade_count] = market_idx; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], trade_market_indices[:trade_count], eligible_markets


@njit(cache=True)
def _evaluate_s15_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1, ret5, ret10, ret30, trade_count_matrix, avail_ret5, avail_ret10, avail_ret30, avail_trade_count, combo,
    entry_slippage,
):
    setup_window_end = int(combo[0]); breakout_scan_start = int(combo[1]); breakout_scan_end = int(combo[2]); breakout_buffer = combo[3]
    confirmation_points = int(combo[4]); feature_window = int(combo[5]); min_underlying_return = combo[6]; min_trade_count = combo[7]; stop_loss = combo[8]; take_profit = combo[9]
    if feature_window == 5:
        ret = ret5; avail_ret = avail_ret5
    elif feature_window == 10:
        ret = ret10; avail_ret = avail_ret10
    else:
        ret = ret30; avail_ret = avail_ret30
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_ret[market_idx] and avail_trade_count[market_idx]):
            continue
        eligible_markets += 1
        start_scan = breakout_scan_start if breakout_scan_start > setup_window_end + 1 else setup_window_end + 1
        if start_scan >= int(total_seconds[market_idx]):
            continue
        last_scan = min(breakout_scan_end, int(total_seconds[market_idx]) - 1)
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(start_scan, last_scan + 1):
            setup_end = setup_window_end if setup_window_end < sec else sec - 1
            setup_values = np.empty(setup_end + 1, dtype=np.float64); count = 0
            for pos in range(0, setup_end + 1):
                value = prices[market_idx, pos]
                if np.isnan(value):
                    continue
                setup_values[count] = value; count += 1
            if count < 6:
                continue
            range_high = setup_values[0]; range_low = setup_values[0]
            for idx in range(1, count):
                value = setup_values[idx]
                if value > range_high: range_high = value
                if value < range_low: range_low = value
            up_price = nearest_tol1[market_idx, sec]; underlying_return = ret[market_idx, sec]; trade_count_v = trade_count_matrix[market_idx, sec]
            if np.isnan(up_price) or np.isnan(underlying_return) or np.isnan(trade_count_v) or trade_count_v < min_trade_count:
                continue
            up_threshold = range_high + breakout_buffer; down_threshold = range_low - breakout_buffer
            if up_price >= up_threshold and underlying_return >= min_underlying_return:
                ok = True
                for check_sec in range(sec - confirmation_points + 1, sec + 1):
                    if check_sec < 0: ok = False; break
                    value = nearest_tol1[market_idx, check_sec]
                    if np.isnan(value) or value < up_threshold: ok = False; break
                if ok:
                    direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
            if up_price <= down_threshold and underlying_return <= -min_underlying_return:
                ok = True
                for check_sec in range(sec - confirmation_points + 1, sec + 1):
                    if check_sec < 0: ok = False; break
                    value = nearest_tol1[market_idx, check_sec]
                    if np.isnan(value) or value > down_threshold: ok = False; break
                if ok:
                    direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], eligible_markets


@njit(cache=True)
def _evaluate_s16_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1, ret5, ret10, ret30, vol10, vol30, avail_ret5, avail_ret10, avail_ret30, avail_v10, avail_v30, combo,
    entry_slippage,
):
    short_window = int(combo[0]); long_window = int(combo[1]); entry_window_start = int(combo[2]); entry_window_end = int(combo[3])
    min_short_return = combo[4]; min_long_return_opposite = combo[5]; min_price_distance_from_mid = combo[6]; max_underlying_vol = combo[7]; stop_loss = combo[8]; take_profit = combo[9]
    short_ret = ret5 if short_window == 5 else ret10
    avail_short = avail_ret5 if short_window == 5 else avail_ret10
    long_ret = ret10 if long_window == 10 else ret30
    avail_long = avail_ret10 if long_window == 10 else avail_ret30
    vol = vol10 if short_window == 5 else vol30
    avail_vol = avail_v10 if short_window == 5 else avail_v30
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_short[market_idx] and avail_long[market_idx] and avail_vol[market_idx]):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]; short_return = short_ret[market_idx, sec]; long_return = long_ret[market_idx, sec]; underlying_vol = vol[market_idx, sec]
            if np.isnan(up_price) or np.isnan(short_return) or np.isnan(long_return) or np.isnan(underlying_vol):
                continue
            if underlying_vol > max_underlying_vol:
                continue
            if short_return >= min_short_return and long_return <= -min_long_return_opposite and up_price <= 0.50 - min_price_distance_from_mid:
                direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
            if short_return <= -min_short_return and long_return >= min_long_return_opposite and up_price >= 0.50 + min_price_distance_from_mid:
                direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], eligible_markets


@njit(cache=True)
def _evaluate_s17_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1, market_delta_open, underlying_return_open, market_delta_5, avail_md_open, avail_ur_open, avail_md5, combo,
    entry_slippage,
):
    entry_window_start = int(combo[0]); entry_window_end = int(combo[1]); underlying_beta = combo[2]; residual_threshold = combo[3]
    min_underlying_move_abs = combo[4]; reversal_confirmation_abs = combo[5]; extreme_price_low = combo[6]; extreme_price_high = combo[7]; stop_loss = combo[8]; take_profit = combo[9]
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_md_open[market_idx] and avail_ur_open[market_idx] and avail_md5[market_idx]):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]; market_delta = market_delta_open[market_idx, sec]; underlying_return = underlying_return_open[market_idx, sec]; reversal_delta = market_delta_5[market_idx, sec]
            if np.isnan(up_price) or np.isnan(market_delta) or np.isnan(underlying_return) or np.isnan(reversal_delta):
                continue
            if abs(underlying_return) < min_underlying_move_abs:
                continue
            expected_market_delta = underlying_beta * underlying_return
            residual = market_delta - expected_market_delta
            if residual >= residual_threshold and up_price >= extreme_price_high and reversal_delta <= -reversal_confirmation_abs:
                direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
            if residual <= -residual_threshold and up_price <= extreme_price_low and reversal_delta >= reversal_confirmation_abs:
                direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], eligible_markets


@njit(cache=True)
def _evaluate_s18_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1, ret5, ret10, ret30, vol30, trade_count_matrix, market_delta_5, avail_ret5, avail_ret10, avail_ret30, avail_vol30, avail_trade_count, avail_md5, combo,
    entry_slippage,
):
    entry_window_start = int(combo[0]); entry_window_end = int(combo[1]); min_return_30s = combo[2]; min_return_10s = combo[3]; min_return_5s = combo[4]
    acceleration_ratio = combo[5]; max_underlying_vol = combo[6]; min_trade_count = combo[7]; max_price_distance_from_mid = combo[8]; stop_loss = combo[9]; take_profit = combo[10]
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_ret5[market_idx] and avail_ret10[market_idx] and avail_ret30[market_idx] and avail_vol30[market_idx] and avail_trade_count[market_idx] and avail_md5[market_idx]):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]; r5 = ret5[market_idx, sec]; r10 = ret10[market_idx, sec]; r30 = ret30[market_idx, sec]; underlying_vol = vol30[market_idx, sec]; trades = trade_count_matrix[market_idx, sec]; md5 = market_delta_5[market_idx, sec]
            if np.isnan(up_price) or np.isnan(r5) or np.isnan(r10) or np.isnan(r30) or np.isnan(underlying_vol) or np.isnan(trades) or np.isnan(md5):
                continue
            if underlying_vol > max_underlying_vol or trades < min_trade_count or abs(up_price - 0.50) > max_price_distance_from_mid:
                continue
            if r30 >= min_return_30s and r10 >= min_return_10s and r5 >= min_return_5s and r5 >= abs(r10) * acceleration_ratio and md5 >= 0.0 and up_price > 0.50:
                direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
            if r30 <= -min_return_30s and r10 <= -min_return_10s and r5 <= -min_return_5s and abs(r5) >= abs(r10) * acceleration_ratio and md5 <= 0.0 and up_price < 0.50:
                direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], eligible_markets


@njit(cache=True)
def _evaluate_s19_combo(
    prices, total_seconds, final_outcomes, asset_codes, duration_minutes, fee_active,
    nearest_tol1, ret5, ret10, ret30, md5, md10, md30, volume, taker_buy, trade_count_matrix,
    avail_ret5, avail_ret10, avail_ret30, avail_md5, avail_md10, avail_md30, avail_volume, avail_taker_buy, avail_trade_count, combo,
    entry_slippage,
):
    entry_window_start = int(combo[0]); entry_window_end = int(combo[1]); feature_window = int(combo[2]); min_underlying_return = combo[3]; min_market_delta = combo[4]; max_market_delta = combo[5]; min_trade_count = combo[6]; min_volume = combo[7]; buy_imbalance_threshold = combo[8]; max_price_distance_from_mid = combo[9]; stop_loss = combo[10]; take_profit = combo[11]
    if feature_window == 5:
        ret = ret5; mdelta = md5; avail_ret = avail_ret5; avail_md = avail_md5
    elif feature_window == 10:
        ret = ret10; mdelta = md10; avail_ret = avail_ret10; avail_md = avail_md10
    else:
        ret = ret30; mdelta = md30; avail_ret = avail_ret30; avail_md = avail_md30
    market_count = prices.shape[0]
    pnls = np.empty(market_count, dtype=np.float64); entry_fees = np.empty(market_count, dtype=np.float64); exit_fees = np.empty(market_count, dtype=np.float64)
    trade_asset_codes = np.empty(market_count, dtype=np.int64); trade_durations = np.empty(market_count, dtype=np.int64)
    trade_count = 0; eligible_markets = 0
    for market_idx in range(market_count):
        if not (avail_ret[market_idx] and avail_md[market_idx] and avail_volume[market_idx] and avail_taker_buy[market_idx] and avail_trade_count[market_idx]):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < entry_window_start:
            continue
        found = False; direction_up = True; adjusted_entry = 0.0; entry_second = -1
        for sec in range(entry_window_start, last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]; underlying_return = ret[market_idx, sec]; market_delta = mdelta[market_idx, sec]; total_volume = volume[market_idx, sec]; taker = taker_buy[market_idx, sec]; trades = trade_count_matrix[market_idx, sec]
            if np.isnan(up_price) or np.isnan(underlying_return) or np.isnan(market_delta) or np.isnan(total_volume) or np.isnan(taker) or np.isnan(trades):
                continue
            if total_volume <= 0.0 or total_volume < min_volume or trades < min_trade_count or abs(up_price - 0.50) > max_price_distance_from_mid:
                continue
            imbalance = ((2.0 * taker) - total_volume) / total_volume
            if imbalance >= buy_imbalance_threshold and underlying_return >= min_underlying_return and min_market_delta <= market_delta <= max_market_delta and up_price > 0.50:
                direction_up = True; adjusted_entry = max(0.01, min(0.99, up_price)); entry_second = sec; found = True; break
            if imbalance <= -buy_imbalance_threshold and underlying_return <= -min_underlying_return and -max_market_delta <= market_delta <= -min_market_delta and up_price < 0.50:
                direction_up = False; adjusted_entry = max(0.01, min(0.99, 1.0 - up_price)); entry_second = sec; found = True; break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(prices, total_seconds, final_outcomes, fee_active, market_idx, entry_second, adjusted_entry, direction_up, stop_loss, take_profit, entry_slippage)
        pnls[trade_count] = pnl; entry_fees[trade_count] = entry_fee; exit_fees[trade_count] = exit_fee; trade_asset_codes[trade_count] = asset_codes[market_idx]; trade_durations[trade_count] = duration_minutes[market_idx]; trade_count += 1
    return pnls[:trade_count], entry_fees[:trade_count], exit_fees[:trade_count], trade_asset_codes[:trade_count], trade_durations[:trade_count], eligible_markets


class _BaseFeatureKernel:
    strategy_id = ""
    strategy_cls = None
    get_default_config = None
    feature_columns = FEATURE_COLUMNS

    def is_available(self) -> bool:
        return NUMBA_AVAILABLE

    def unavailable_reason(self) -> str:
        return NUMBA_IMPORT_ERROR or "Numba is not installed."

    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        return PrecomputedDataset(
            strategy_id=strategy_id,
            markets=markets,
            payload=_build_feature_payload(markets, self.feature_columns),
            eligible_markets=len(markets),
            skipped_markets_missing_features=0,
        )

    def materialize_trades(self, dataset: PrecomputedDataset, param_dict: dict[str, object], config_id: str) -> list[Trade]:
        base_config = self.get_default_config()
        config_fields = {field.name for field in dataclasses.fields(type(base_config))}
        strategy_params = {key: value for key, value in param_dict.items() if key in config_fields}
        exit_params = {key: value for key, value in param_dict.items() if key not in config_fields}
        strategy = self.strategy_cls(dataclasses.replace(base_config, **strategy_params))
        trades, _ = run_strategy(config_id, strategy, dataset.markets, slippage=dataset.slippage, stop_loss=exit_params.get("stop_loss"), take_profit=exit_params.get("take_profit"), log_summary=False)
        return trades


def _metrics_with_eligible(result, config_id, dataset, param_dict):
    if len(result) == 7:
        pnls, entry_fees, exit_fees, asset_codes, durations, _, eligible_markets = result
    else:
        pnls, entry_fees, exit_fees, asset_codes, durations, eligible_markets = result
    metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
    metrics["eligible_markets"] = int(eligible_markets)
    metrics["skipped_markets_missing_features"] = int(len(dataset.markets) - eligible_markets)
    metrics.update(param_dict)
    return metrics


class S13Accelerator(_BaseFeatureKernel):
    strategy_id = "S13"; strategy_cls = S13Strategy; get_default_config = staticmethod(get_s13_default_config)
    def prepare(self, strategy_id: str, markets: list[dict], param_grid: dict[str, list]) -> PrecomputedDataset:
        return PrecomputedDataset(
            strategy_id=strategy_id,
            markets=markets,
            payload=_build_s13_payload(markets),
            eligible_markets=len(markets),
            skipped_markets_missing_features=0,
        )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: S13Payload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s13_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.ret5,
                p.ret10,
                p.ret30,
                p.m5,
                p.m10,
                p.m30,
                p.vol10,
                p.vol30,
                p.avail_ret5,
                p.avail_ret10,
                p.avail_ret30,
                p.avail_m5,
                p.avail_m10,
                p.avail_m30,
                p.avail_v10,
                p.avail_v30,
                combo_array,
                dataset.slippage,
            )
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S14Accelerator(_BaseFeatureKernel):
    strategy_id = "S14"; strategy_cls = S14Strategy; get_default_config = staticmethod(get_s14_default_config)
    feature_columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "market_up_delta_5s",
        "market_up_delta_10s",
        "market_up_delta_30s",
        "direction_mismatch_5s",
        "direction_mismatch_10s",
        "direction_mismatch_30s",
    )
    def encode_combo(self, combo):
        values = list(combo); values[7] = 1.0 if combo[7] else 0.0; return np.array(values, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s14_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["underlying_return_5s"], p.matrices["underlying_return_10s"], p.matrices["underlying_return_30s"], p.matrices["market_up_delta_5s"], p.matrices["market_up_delta_10s"], p.matrices["market_up_delta_30s"], p.matrices["direction_mismatch_5s"], p.matrices["direction_mismatch_10s"], p.matrices["direction_mismatch_30s"], p.availability["underlying_return_5s"], p.availability["underlying_return_10s"], p.availability["underlying_return_30s"], p.availability["market_up_delta_5s"], p.availability["market_up_delta_10s"], p.availability["market_up_delta_30s"], p.availability["direction_mismatch_5s"], p.availability["direction_mismatch_10s"], p.availability["direction_mismatch_30s"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S15Accelerator(_BaseFeatureKernel):
    strategy_id = "S15"; strategy_cls = S15Strategy; get_default_config = staticmethod(get_s15_default_config)
    feature_columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "underlying_trade_count",
    )
    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s15_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["underlying_return_5s"], p.matrices["underlying_return_10s"], p.matrices["underlying_return_30s"], p.matrices["underlying_trade_count"], p.availability["underlying_return_5s"], p.availability["underlying_return_10s"], p.availability["underlying_return_30s"], p.availability["underlying_trade_count"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S16Accelerator(_BaseFeatureKernel):
    strategy_id = "S16"; strategy_cls = S16Strategy; get_default_config = staticmethod(get_s16_default_config)
    feature_columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "underlying_realized_vol_10s",
        "underlying_realized_vol_30s",
    )
    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s16_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["underlying_return_5s"], p.matrices["underlying_return_10s"], p.matrices["underlying_return_30s"], p.matrices["underlying_realized_vol_10s"], p.matrices["underlying_realized_vol_30s"], p.availability["underlying_return_5s"], p.availability["underlying_return_10s"], p.availability["underlying_return_30s"], p.availability["underlying_realized_vol_10s"], p.availability["underlying_realized_vol_30s"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S17Accelerator(_BaseFeatureKernel):
    strategy_id = "S17"; strategy_cls = S17Strategy; get_default_config = staticmethod(get_s17_default_config)
    feature_columns = (
        "market_up_delta_from_market_open",
        "underlying_return_from_market_open",
        "market_up_delta_5s",
    )
    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s17_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["market_up_delta_from_market_open"], p.matrices["underlying_return_from_market_open"], p.matrices["market_up_delta_5s"], p.availability["market_up_delta_from_market_open"], p.availability["underlying_return_from_market_open"], p.availability["market_up_delta_5s"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S18Accelerator(_BaseFeatureKernel):
    strategy_id = "S18"; strategy_cls = S18Strategy; get_default_config = staticmethod(get_s18_default_config)
    feature_columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "underlying_realized_vol_30s",
        "underlying_trade_count",
        "market_up_delta_5s",
    )
    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s18_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["underlying_return_5s"], p.matrices["underlying_return_10s"], p.matrices["underlying_return_30s"], p.matrices["underlying_realized_vol_30s"], p.matrices["underlying_trade_count"], p.matrices["market_up_delta_5s"], p.availability["underlying_return_5s"], p.availability["underlying_return_10s"], p.availability["underlying_return_30s"], p.availability["underlying_realized_vol_30s"], p.availability["underlying_trade_count"], p.availability["market_up_delta_5s"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r


class S19Accelerator(_BaseFeatureKernel):
    strategy_id = "S19"; strategy_cls = S19Strategy; get_default_config = staticmethod(get_s19_default_config)
    feature_columns = (
        "underlying_return_5s",
        "underlying_return_10s",
        "underlying_return_30s",
        "market_up_delta_5s",
        "market_up_delta_10s",
        "market_up_delta_30s",
        "underlying_volume",
        "underlying_taker_buy_base_volume",
        "underlying_trade_count",
    )
    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)
    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload; r = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values)); config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s19_combo(p.common.prices, p.common.total_seconds, p.common.final_outcomes, p.common.asset_codes, p.common.duration_minutes, p.common.fee_active, p.nearest_tol1, p.matrices["underlying_return_5s"], p.matrices["underlying_return_10s"], p.matrices["underlying_return_30s"], p.matrices["market_up_delta_5s"], p.matrices["market_up_delta_10s"], p.matrices["market_up_delta_30s"], p.matrices["underlying_volume"], p.matrices["underlying_taker_buy_base_volume"], p.matrices["underlying_trade_count"], p.availability["underlying_return_5s"], p.availability["underlying_return_10s"], p.availability["underlying_return_30s"], p.availability["market_up_delta_5s"], p.availability["market_up_delta_10s"], p.availability["market_up_delta_30s"], p.availability["underlying_volume"], p.availability["underlying_taker_buy_base_volume"], p.availability["underlying_trade_count"], combo_array, dataset.slippage)
            r.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return r
