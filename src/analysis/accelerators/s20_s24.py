"""Accelerated optimization kernels for strategies S20 through S24."""

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
from shared.strategies.S20.config import get_default_config as get_s20_default_config
from shared.strategies.S20.strategy import S20Strategy
from shared.strategies.S21.config import get_default_config as get_s21_default_config
from shared.strategies.S21.strategy import S21Strategy
from shared.strategies.S22.config import get_default_config as get_s22_default_config
from shared.strategies.S22.strategy import S22Strategy
from shared.strategies.S23.config import get_default_config as get_s23_default_config
from shared.strategies.S23.strategy import S23Strategy
from shared.strategies.S24.config import get_default_config as get_s24_default_config
from shared.strategies.S24.strategy import S24Strategy


@dataclass
class FeaturePayload:
    common: object
    nearest_tol1: np.ndarray
    matrices: dict[str, np.ndarray]
    availability: dict[str, np.ndarray]


FEATURE_COLUMNS = (
    "underlying_return_from_market_open",
    "market_up_delta_from_market_open",
    "underlying_return_5s",
    "market_up_delta_5s",
    "underlying_trade_count",
    "underlying_volume",
)


def _build_feature_payload(markets: list[dict], columns: tuple[str, ...] = FEATURE_COLUMNS) -> FeaturePayload:
    common = build_common_payload(markets)
    nearest_tol1 = precompute_nearest_prices_multi(
        common.prices,
        common.total_seconds,
        np.array([1], dtype=np.int64),
    )[0]

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

    return FeaturePayload(
        common=common,
        nearest_tol1=nearest_tol1,
        matrices=matrices,
        availability=availability,
    )


@njit(cache=True)
def _checkpoint_hit(remaining_seconds: int, duration_minutes: int, tolerance: int) -> bool:
    if duration_minutes == 5:
        return (
            abs(remaining_seconds - 60) <= tolerance
            or abs(remaining_seconds - 30) <= tolerance
            or abs(remaining_seconds - 15) <= tolerance
        )
    if duration_minutes == 15:
        return (
            abs(remaining_seconds - 300) <= tolerance
            or abs(remaining_seconds - 240) <= tolerance
            or abs(remaining_seconds - 180) <= tolerance
        )
    if duration_minutes == 60:
        return (
            abs(remaining_seconds - 900) <= tolerance
            or abs(remaining_seconds - 600) <= tolerance
            or abs(remaining_seconds - 300) <= tolerance
        )
    if duration_minutes == 240:
        return (
            abs(remaining_seconds - 7200) <= tolerance
            or abs(remaining_seconds - 6300) <= tolerance
            or abs(remaining_seconds - 5400) <= tolerance
            or abs(remaining_seconds - 4500) <= tolerance
            or abs(remaining_seconds - 3600) <= tolerance
            or abs(remaining_seconds - 2700) <= tolerance
            or abs(remaining_seconds - 1800) <= tolerance
            or abs(remaining_seconds - 900) <= tolerance
        )
    return False


@njit(cache=True)
def _evaluate_s20_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret_open,
    market_open,
    ret5,
    avail_ret_open,
    avail_market_open,
    avail_ret5,
    combo,
    entry_slippage,
):
    checkpoint_tolerance = int(combo[0])
    min_underlying_return_open = combo[1]
    min_recent_return_5s = combo[2]
    underlying_beta = combo[3]
    min_directional_gap = combo[4]
    min_market_delta_open = combo[5]
    max_entry_price = combo[6]
    stop_loss = combo[7]
    take_profit = combo[8]

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
        if not (avail_ret_open[market_idx] and avail_market_open[market_idx] and avail_ret5[market_idx]):
            continue
        eligible_markets += 1
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(int(total_seconds[market_idx])):
            remaining_seconds = int(total_seconds[market_idx]) - 1 - sec
            if remaining_seconds < 0 or not _checkpoint_hit(remaining_seconds, int(duration_minutes[market_idx]), checkpoint_tolerance):
                continue
            up_price = nearest_tol1[market_idx, sec]
            underlying_return_open = ret_open[market_idx, sec]
            market_delta_open = market_open[market_idx, sec]
            recent_return = ret5[market_idx, sec]
            if np.isnan(up_price) or np.isnan(underlying_return_open) or np.isnan(market_delta_open) or np.isnan(recent_return):
                continue
            direction_sign = 1
            if underlying_return_open < 0.0:
                direction_sign = -1
            elif underlying_return_open == 0.0:
                continue
            if abs(underlying_return_open) < min_underlying_return_open:
                continue
            if direction_sign * recent_return < min_recent_return_5s:
                continue
            if direction_sign * market_delta_open < min_market_delta_open:
                continue
            expected_market_delta = underlying_beta * underlying_return_open
            directional_gap = direction_sign * (expected_market_delta - market_delta_open)
            if directional_gap < min_directional_gap:
                continue
            token_price = up_price if direction_sign > 0 else 1.0 - up_price
            token_price = max(0.01, min(0.99, token_price))
            if token_price > max_entry_price:
                continue
            direction_up = direction_sign > 0
            adjusted_entry = token_price
            entry_second = sec
            found = True
            break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices,
            total_seconds,
            final_outcomes,
            fee_active,
            market_idx,
            entry_second,
            adjusted_entry,
            direction_up,
            stop_loss,
            take_profit,
            entry_slippage,
        )
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
def _evaluate_s21_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret_open,
    market_open,
    ret5,
    market5,
    trade_count_matrix,
    avail_ret_open,
    avail_market_open,
    avail_ret5,
    avail_market5,
    avail_trade_count,
    combo,
    entry_slippage,
):
    max_seconds_to_close = int(combo[0])
    min_seconds_to_close = int(combo[1])
    min_underlying_return_open = combo[2]
    min_recent_underlying_return_5s = combo[3]
    min_recent_market_delta_5s = combo[4]
    min_market_delta_open = combo[5]
    min_trade_count = combo[6]
    max_entry_price = combo[7]
    stop_loss = combo[8]
    take_profit = combo[9]

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
        if not (
            avail_ret_open[market_idx]
            and avail_market_open[market_idx]
            and avail_ret5[market_idx]
            and avail_market5[market_idx]
            and avail_trade_count[market_idx]
        ):
            continue
        eligible_markets += 1
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(int(total_seconds[market_idx])):
            remaining_seconds = int(total_seconds[market_idx]) - 1 - sec
            if remaining_seconds > max_seconds_to_close or remaining_seconds < min_seconds_to_close:
                continue
            up_price = nearest_tol1[market_idx, sec]
            underlying_return_open = ret_open[market_idx, sec]
            market_delta_open = market_open[market_idx, sec]
            recent_return = ret5[market_idx, sec]
            recent_market_delta = market5[market_idx, sec]
            trades = trade_count_matrix[market_idx, sec]
            if (
                np.isnan(up_price)
                or np.isnan(underlying_return_open)
                or np.isnan(market_delta_open)
                or np.isnan(recent_return)
                or np.isnan(recent_market_delta)
                or np.isnan(trades)
            ):
                continue
            direction_sign = 1
            if underlying_return_open < 0.0:
                direction_sign = -1
            elif underlying_return_open == 0.0:
                continue
            if abs(underlying_return_open) < min_underlying_return_open:
                continue
            if direction_sign * recent_return < min_recent_underlying_return_5s:
                continue
            if direction_sign * recent_market_delta < min_recent_market_delta_5s:
                continue
            if direction_sign * market_delta_open < min_market_delta_open:
                continue
            if trades < min_trade_count:
                continue
            token_price = up_price if direction_sign > 0 else 1.0 - up_price
            token_price = max(0.01, min(0.99, token_price))
            if token_price > max_entry_price:
                continue
            direction_up = direction_sign > 0
            adjusted_entry = token_price
            entry_second = sec
            found = True
            break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices,
            total_seconds,
            final_outcomes,
            fee_active,
            market_idx,
            entry_second,
            adjusted_entry,
            direction_up,
            stop_loss,
            take_profit,
            entry_slippage,
        )
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
def _evaluate_s22_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret_open,
    market_open,
    ret5,
    trade_count_matrix,
    avail_ret_open,
    avail_market_open,
    avail_ret5,
    avail_trade_count,
    combo,
    entry_slippage,
):
    max_seconds_to_close = int(combo[0])
    min_seconds_to_close = int(combo[1])
    min_lead_return_open = combo[2]
    max_lead_return_open = combo[3]
    min_recent_return_5s = combo[4]
    min_market_delta_open = combo[5]
    min_trade_count = combo[6]
    entry_price_floor = combo[7]
    entry_price_cap = combo[8]
    stop_loss = combo[9]
    take_profit = combo[10]

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
        if not (
            avail_ret_open[market_idx]
            and avail_market_open[market_idx]
            and avail_ret5[market_idx]
            and avail_trade_count[market_idx]
        ):
            continue
        eligible_markets += 1
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(int(total_seconds[market_idx])):
            remaining_seconds = int(total_seconds[market_idx]) - 1 - sec
            if remaining_seconds > max_seconds_to_close or remaining_seconds < min_seconds_to_close:
                continue
            up_price = nearest_tol1[market_idx, sec]
            underlying_return_open = ret_open[market_idx, sec]
            market_delta_open = market_open[market_idx, sec]
            recent_return = ret5[market_idx, sec]
            trades = trade_count_matrix[market_idx, sec]
            if (
                np.isnan(up_price)
                or np.isnan(underlying_return_open)
                or np.isnan(market_delta_open)
                or np.isnan(recent_return)
                or np.isnan(trades)
            ):
                continue
            lead_abs = abs(underlying_return_open)
            if lead_abs < min_lead_return_open or lead_abs > max_lead_return_open:
                continue
            direction_sign = 1
            if underlying_return_open < 0.0:
                direction_sign = -1
            elif underlying_return_open == 0.0:
                continue
            if direction_sign * recent_return < min_recent_return_5s:
                continue
            if direction_sign * market_delta_open < min_market_delta_open:
                continue
            if trades < min_trade_count:
                continue
            token_price = up_price if direction_sign > 0 else 1.0 - up_price
            token_price = max(0.01, min(0.99, token_price))
            if token_price < entry_price_floor or token_price > entry_price_cap:
                continue
            direction_up = direction_sign > 0
            adjusted_entry = token_price
            entry_second = sec
            found = True
            break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices,
            total_seconds,
            final_outcomes,
            fee_active,
            market_idx,
            entry_second,
            adjusted_entry,
            direction_up,
            stop_loss,
            take_profit,
            entry_slippage,
        )
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
def _evaluate_s23_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret_open,
    market_open,
    ret5,
    trade_count_matrix,
    avail_ret_open,
    avail_market_open,
    avail_ret5,
    avail_trade_count,
    combo,
    entry_slippage,
):
    entry_window_start = int(combo[0])
    entry_window_end = int(combo[1])
    trigger_return_from_open = combo[2]
    pre_trigger_buffer = combo[3]
    min_recent_return_5s = combo[4]
    max_market_delta_open = combo[5]
    min_trade_count = combo[6]
    max_entry_price = combo[7]
    stop_loss = combo[8]
    take_profit = combo[9]

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
        if not (
            avail_ret_open[market_idx]
            and avail_market_open[market_idx]
            and avail_ret5[market_idx]
            and avail_trade_count[market_idx]
        ):
            continue
        eligible_markets += 1
        last_entry = min(entry_window_end, int(total_seconds[market_idx]) - 1)
        if last_entry < max(1, entry_window_start):
            continue
        found = False
        direction_up = True
        adjusted_entry = 0.0
        entry_second = -1
        for sec in range(max(1, entry_window_start), last_entry + 1):
            up_price = nearest_tol1[market_idx, sec]
            current_return_open = ret_open[market_idx, sec]
            previous_return_open = ret_open[market_idx, sec - 1]
            market_delta_open = market_open[market_idx, sec]
            recent_return = ret5[market_idx, sec]
            trades = trade_count_matrix[market_idx, sec]
            if (
                np.isnan(up_price)
                or np.isnan(current_return_open)
                or np.isnan(previous_return_open)
                or np.isnan(market_delta_open)
                or np.isnan(recent_return)
                or np.isnan(trades)
            ):
                continue
            if trades < min_trade_count:
                continue
            if (
                previous_return_open < trigger_return_from_open
                and previous_return_open >= trigger_return_from_open - pre_trigger_buffer
                and current_return_open >= trigger_return_from_open
                and recent_return >= min_recent_return_5s
                and market_delta_open >= 0.0
                and market_delta_open <= max_market_delta_open
            ):
                token_price = max(0.01, min(0.99, up_price))
                if token_price > max_entry_price:
                    continue
                direction_up = True
                adjusted_entry = token_price
                entry_second = sec
                found = True
                break
            if (
                previous_return_open > -trigger_return_from_open
                and previous_return_open <= -trigger_return_from_open + pre_trigger_buffer
                and current_return_open <= -trigger_return_from_open
                and recent_return <= -min_recent_return_5s
                and market_delta_open <= 0.0
                and market_delta_open >= -max_market_delta_open
            ):
                token_price = max(0.01, min(0.99, 1.0 - up_price))
                if token_price > max_entry_price:
                    continue
                direction_up = False
                adjusted_entry = token_price
                entry_second = sec
                found = True
                break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices,
            total_seconds,
            final_outcomes,
            fee_active,
            market_idx,
            entry_second,
            adjusted_entry,
            direction_up,
            stop_loss,
            take_profit,
            entry_slippage,
        )
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
def _evaluate_s24_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret_open,
    market_open,
    ret5,
    trade_count_matrix,
    volume,
    avail_ret_open,
    avail_market_open,
    avail_ret5,
    avail_trade_count,
    avail_volume,
    combo,
    entry_slippage,
):
    entry_window_start = int(combo[0])
    entry_window_end = int(combo[1])
    min_underlying_return_open = combo[2]
    min_recent_return_5s = combo[3]
    min_market_delta_open = combo[4]
    max_market_delta_open = combo[5]
    min_trade_count = combo[6]
    min_volume = combo[7]
    max_entry_price = combo[8]
    stop_loss = combo[9]
    take_profit = combo[10]

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
        if not (
            avail_ret_open[market_idx]
            and avail_market_open[market_idx]
            and avail_ret5[market_idx]
            and avail_trade_count[market_idx]
            and avail_volume[market_idx]
        ):
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
            underlying_return_open = ret_open[market_idx, sec]
            market_delta_open = market_open[market_idx, sec]
            recent_return = ret5[market_idx, sec]
            trades = trade_count_matrix[market_idx, sec]
            total_volume = volume[market_idx, sec]
            if (
                np.isnan(up_price)
                or np.isnan(underlying_return_open)
                or np.isnan(market_delta_open)
                or np.isnan(recent_return)
                or np.isnan(trades)
                or np.isnan(total_volume)
            ):
                continue
            direction_sign = 1
            if underlying_return_open < 0.0:
                direction_sign = -1
            elif underlying_return_open == 0.0:
                continue
            if abs(underlying_return_open) < min_underlying_return_open:
                continue
            if direction_sign * recent_return < min_recent_return_5s:
                continue
            directional_market_delta = direction_sign * market_delta_open
            if directional_market_delta < min_market_delta_open:
                continue
            if directional_market_delta > max_market_delta_open:
                continue
            if trades < min_trade_count or total_volume < min_volume:
                continue
            token_price = up_price if direction_sign > 0 else 1.0 - up_price
            token_price = max(0.01, min(0.99, token_price))
            if token_price > max_entry_price:
                continue
            direction_up = direction_sign > 0
            adjusted_entry = token_price
            entry_second = sec
            found = True
            break
        if not found:
            continue
        pnl, entry_fee, exit_fee = resolve_trade_pnl(
            prices,
            total_seconds,
            final_outcomes,
            fee_active,
            market_idx,
            entry_second,
            adjusted_entry,
            direction_up,
            stop_loss,
            take_profit,
            entry_slippage,
        )
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


def _metrics_with_eligible(result, config_id, dataset, param_dict):
    pnls, entry_fees, exit_fees, asset_codes, durations, _, eligible_markets = result
    metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
    metrics["eligible_markets"] = int(eligible_markets)
    metrics["skipped_markets_missing_features"] = int(len(dataset.markets) - eligible_markets)
    metrics.update(param_dict)
    return metrics


class S20Accelerator(_BaseFeatureKernel):
    strategy_id = "S20"
    strategy_cls = S20Strategy
    get_default_config = staticmethod(get_s20_default_config)
    feature_columns = (
        "underlying_return_from_market_open",
        "market_up_delta_from_market_open",
        "underlying_return_5s",
    )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s20_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_from_market_open"],
                p.matrices["market_up_delta_from_market_open"],
                p.matrices["underlying_return_5s"],
                p.availability["underlying_return_from_market_open"],
                p.availability["market_up_delta_from_market_open"],
                p.availability["underlying_return_5s"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows


class S21Accelerator(_BaseFeatureKernel):
    strategy_id = "S21"
    strategy_cls = S21Strategy
    get_default_config = staticmethod(get_s21_default_config)
    feature_columns = (
        "underlying_return_from_market_open",
        "market_up_delta_from_market_open",
        "underlying_return_5s",
        "market_up_delta_5s",
        "underlying_trade_count",
    )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s21_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_from_market_open"],
                p.matrices["market_up_delta_from_market_open"],
                p.matrices["underlying_return_5s"],
                p.matrices["market_up_delta_5s"],
                p.matrices["underlying_trade_count"],
                p.availability["underlying_return_from_market_open"],
                p.availability["market_up_delta_from_market_open"],
                p.availability["underlying_return_5s"],
                p.availability["market_up_delta_5s"],
                p.availability["underlying_trade_count"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows


class S22Accelerator(_BaseFeatureKernel):
    strategy_id = "S22"
    strategy_cls = S22Strategy
    get_default_config = staticmethod(get_s22_default_config)
    feature_columns = (
        "underlying_return_from_market_open",
        "market_up_delta_from_market_open",
        "underlying_return_5s",
        "underlying_trade_count",
    )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s22_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_from_market_open"],
                p.matrices["market_up_delta_from_market_open"],
                p.matrices["underlying_return_5s"],
                p.matrices["underlying_trade_count"],
                p.availability["underlying_return_from_market_open"],
                p.availability["market_up_delta_from_market_open"],
                p.availability["underlying_return_5s"],
                p.availability["underlying_trade_count"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows


class S23Accelerator(_BaseFeatureKernel):
    strategy_id = "S23"
    strategy_cls = S23Strategy
    get_default_config = staticmethod(get_s23_default_config)
    feature_columns = (
        "underlying_return_from_market_open",
        "market_up_delta_from_market_open",
        "underlying_return_5s",
        "underlying_trade_count",
    )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s23_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_from_market_open"],
                p.matrices["market_up_delta_from_market_open"],
                p.matrices["underlying_return_5s"],
                p.matrices["underlying_trade_count"],
                p.availability["underlying_return_from_market_open"],
                p.availability["market_up_delta_from_market_open"],
                p.availability["underlying_return_5s"],
                p.availability["underlying_trade_count"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows


class S24Accelerator(_BaseFeatureKernel):
    strategy_id = "S24"
    strategy_cls = S24Strategy
    get_default_config = staticmethod(get_s24_default_config)
    feature_columns = (
        "underlying_return_from_market_open",
        "market_up_delta_from_market_open",
        "underlying_return_5s",
        "underlying_trade_count",
        "underlying_volume",
    )

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s24_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_from_market_open"],
                p.matrices["market_up_delta_from_market_open"],
                p.matrices["underlying_return_5s"],
                p.matrices["underlying_trade_count"],
                p.matrices["underlying_volume"],
                p.availability["underlying_return_from_market_open"],
                p.availability["market_up_delta_from_market_open"],
                p.availability["underlying_return_5s"],
                p.availability["underlying_trade_count"],
                p.availability["underlying_volume"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows
