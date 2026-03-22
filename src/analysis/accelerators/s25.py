"""Accelerated optimization kernel for strategy S25."""

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
from shared.strategies.S25.config import get_default_config as get_s25_default_config
from shared.strategies.S25.strategy import S25Strategy


FEATURE_COLUMNS = (
    "underlying_return_5s",
    "market_up_delta_5s",
    "underlying_trade_count",
)


@dataclass
class FeaturePayload:
    common: object
    nearest_tol1: np.ndarray
    matrices: dict[str, np.ndarray]
    availability: dict[str, np.ndarray]


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
def _evaluate_s25_combo(
    prices,
    total_seconds,
    final_outcomes,
    asset_codes,
    duration_minutes,
    fee_active,
    nearest_tol1,
    ret5,
    market5,
    trade_count_matrix,
    avail_ret5,
    avail_market5,
    avail_trade_count,
    combo,
    entry_slippage,
):
    checkpoint_tolerance = int(combo[0])
    min_underlying_return_5s = combo[1]
    underlying_beta = combo[2]
    min_directional_gap = combo[3]
    min_market_delta_5s = combo[4]
    min_trade_count = combo[5]
    min_price_distance_from_mid = combo[6]
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
        if not (avail_ret5[market_idx] and avail_market5[market_idx] and avail_trade_count[market_idx]):
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
            underlying_return_5s = ret5[market_idx, sec]
            market_delta_5s = market5[market_idx, sec]
            trades = trade_count_matrix[market_idx, sec]
            if (
                np.isnan(up_price)
                or np.isnan(underlying_return_5s)
                or np.isnan(market_delta_5s)
                or np.isnan(trades)
            ):
                continue
            direction_sign = 1
            if underlying_return_5s < 0.0:
                direction_sign = -1
            elif underlying_return_5s == 0.0:
                continue
            if abs(underlying_return_5s) < min_underlying_return_5s:
                continue
            if direction_sign * market_delta_5s < min_market_delta_5s:
                continue
            if trades < min_trade_count:
                continue
            if abs(up_price - 0.50) < min_price_distance_from_mid:
                continue
            expected_market_delta = underlying_beta * underlying_return_5s
            directional_gap = direction_sign * (expected_market_delta - market_delta_5s)
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


def _metrics_with_eligible(result, config_id, dataset, param_dict):
    pnls, entry_fees, exit_fees, asset_codes, durations, _, eligible_markets = result
    metrics = compute_metrics_from_arrays(pnls, entry_fees, exit_fees, asset_codes, durations, config_id)
    metrics["eligible_markets"] = int(eligible_markets)
    metrics["skipped_markets_missing_features"] = int(len(dataset.markets) - eligible_markets)
    metrics.update(param_dict)
    return metrics


class S25Accelerator:
    strategy_id = "S25"
    strategy_cls = S25Strategy
    get_default_config = staticmethod(get_s25_default_config)
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

    def encode_combo(self, combo): return np.array(combo, dtype=np.float64)

    def evaluate_batch(self, dataset, encoded_batch, combo_batch, param_names, config_id_builder):
        p: FeaturePayload = dataset.payload
        rows = []
        for combo_array, combo_values in zip(encoded_batch, combo_batch):
            param_dict = dict(zip(param_names, combo_values))
            config_id = config_id_builder(dataset.strategy_id, param_dict)
            result = _evaluate_s25_combo(
                p.common.prices,
                p.common.total_seconds,
                p.common.final_outcomes,
                p.common.asset_codes,
                p.common.duration_minutes,
                p.common.fee_active,
                p.nearest_tol1,
                p.matrices["underlying_return_5s"],
                p.matrices["market_up_delta_5s"],
                p.matrices["underlying_trade_count"],
                p.availability["underlying_return_5s"],
                p.availability["market_up_delta_5s"],
                p.availability["underlying_trade_count"],
                combo_array,
                dataset.slippage,
            )
            rows.append(_metrics_with_eligible(result, config_id, dataset, param_dict))
        return rows

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
