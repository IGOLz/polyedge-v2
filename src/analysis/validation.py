"""Validation helpers for fixed strategy candidates.

This module focuses on validating a small number of promising configurations
without re-running a full grid search. It is designed for iterative strategy
development: optimize a strategy, pick one or a few candidates, then run a
deeper fixed-config validation suite before making live-trading decisions.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.accelerators import get_strategy_kernel
from analysis.accelerators.base import PrecomputedDataset, compute_metrics_from_arrays
from analysis.accelerators.s2_s6 import _evaluate_s3_combo, _evaluate_s5_combo
from analysis.backtest.engine import compute_metrics, make_trade
from analysis.backtest_strategies import market_to_snapshot, run_strategy
from shared.strategies.helpers import get_price
from shared.strategies.registry import discover_strategies

DEFAULT_SLIPPAGE_GRID = (0.00, 0.01, 0.02, 0.03)
DEFAULT_ENTRY_DELAYS = (0,)
DEFAULT_FOLD_COUNT = 6
DEFAULT_BOOTSTRAP_ITERATIONS = 1000


@dataclass
class StrategyRuntime:
    """Loaded runtime components for a strategy."""

    strategy_cls: type
    base_config: Any
    config_fields: set[str]
    param_grid: dict[str, list[Any]]


@dataclass
class StrategyCandidate:
    """A fixed configuration selected for deeper validation."""

    strategy_id: str
    param_dict: dict[str, Any]
    config_id: str | None = None
    source_label: str | None = None
    rank: int | None = None

    @property
    def label(self) -> str:
        if self.config_id:
            return self.config_id
        parts = [f"{key}={value}" for key, value in self.param_dict.items()]
        return f"{self.strategy_id}_{'_'.join(parts)}"


@dataclass
class CandidateRun:
    """Results of executing a fixed candidate."""

    trades: list
    metrics: dict[str, Any]
    eligible_market_ids: set[str]
    skipped_markets_missing_features: int
    execution_stats: dict[str, int]
    pnls: np.ndarray | None = None
    entry_fees: np.ndarray | None = None
    exit_fees: np.ndarray | None = None
    asset_codes: np.ndarray | None = None
    duration_values: np.ndarray | None = None
    trade_market_indices: np.ndarray | None = None
    market_ids_by_index: list[str] | None = None
    asset_code_labels: dict[int, str] | None = None
    accelerated: bool = False


@dataclass
class AcceleratedContext:
    """Prepared accelerated dataset for repeated candidate validation."""

    strategy_id: str
    runtime: StrategyRuntime
    kernel: Any
    dataset: PrecomputedDataset
    param_names: list[str]
    asset_code_labels: dict[int, str]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_python(value: Any) -> Any:
    """Convert numpy/pandas scalars to plain Python types."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def _value_matches(raw_value: Any, candidate_value: Any) -> bool:
    """Return whether *raw_value* matches *candidate_value* from the grid."""
    raw_value = _to_python(raw_value)
    candidate_value = _to_python(candidate_value)

    if pd.isna(raw_value):
        return candidate_value is None

    if isinstance(candidate_value, list):
        if isinstance(raw_value, str):
            try:
                return ast.literal_eval(raw_value) == candidate_value
            except (ValueError, SyntaxError):
                return raw_value == str(candidate_value)
        return raw_value == candidate_value

    if candidate_value is None:
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"none", "null", "nan"}
        return False

    if isinstance(candidate_value, bool):
        if isinstance(raw_value, str):
            return raw_value.strip().lower() == str(candidate_value).lower()
        return bool(raw_value) is candidate_value

    if isinstance(candidate_value, (int, float)):
        try:
            return float(raw_value) == float(candidate_value)
        except (TypeError, ValueError):
            return False

    return raw_value == candidate_value or str(raw_value) == str(candidate_value)


def _coerce_from_grid(raw_value: Any, allowed_values: list[Any]) -> Any:
    """Coerce a CSV value back to the matching object from the parameter grid."""
    for allowed in allowed_values:
        if _value_matches(raw_value, allowed):
            return allowed

    if pd.isna(raw_value):
        return None

    if isinstance(raw_value, str):
        try:
            return ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            return raw_value

    return _to_python(raw_value)


def load_strategy_runtime(strategy_id: str) -> StrategyRuntime:
    """Load the shared strategy class, default config, and parameter grid."""
    registry = discover_strategies()
    if strategy_id not in registry:
        raise KeyError(
            f"Strategy '{strategy_id}' not found. Available: {sorted(registry.keys())}"
        )

    config_module = importlib.import_module(f"shared.strategies.{strategy_id}.config")
    param_grid = getattr(config_module, "get_param_grid", lambda: {})()
    base_config = config_module.get_default_config()
    config_fields = {field.name for field in dataclasses.fields(type(base_config))}
    return StrategyRuntime(
        strategy_cls=registry[strategy_id],
        base_config=base_config,
        config_fields=config_fields,
        param_grid=param_grid,
    )


def candidate_from_results_csv(
    strategy_id: str,
    csv_path: str | Path,
    rank: int = 1,
) -> StrategyCandidate:
    """Load a fixed candidate from an optimizer CSV output."""
    if rank < 1:
        raise ValueError("rank must be >= 1")

    runtime = load_strategy_runtime(strategy_id)
    df = pd.read_csv(csv_path)
    if rank > len(df):
        raise ValueError(f"rank {rank} out of range for {len(df)} rows")

    row = df.iloc[rank - 1]
    param_dict: dict[str, Any] = {}
    for param_name, allowed_values in runtime.param_grid.items():
        if param_name not in row:
            continue
        param_dict[param_name] = _coerce_from_grid(row[param_name], allowed_values)

    return StrategyCandidate(
        strategy_id=strategy_id,
        param_dict=param_dict,
        config_id=str(row.get("config_id")) if "config_id" in row else None,
        source_label=str(csv_path),
        rank=rank,
    )


def build_candidate(
    candidate: StrategyCandidate,
) -> tuple[Any, dict[str, Any], StrategyRuntime]:
    """Instantiate a strategy from a fixed candidate."""
    runtime = load_strategy_runtime(candidate.strategy_id)
    strategy_params = {
        key: value
        for key, value in candidate.param_dict.items()
        if key in runtime.config_fields
    }
    exit_params = {
        key: value
        for key, value in candidate.param_dict.items()
        if key not in runtime.config_fields
    }
    config = dataclasses.replace(runtime.base_config, **strategy_params)
    strategy = runtime.strategy_cls(config)
    return strategy, exit_params, runtime


def compare_candidate_to_defaults(candidate: StrategyCandidate) -> list[dict[str, Any]]:
    """Compare a candidate against the live/default strategy configuration."""
    runtime = load_strategy_runtime(candidate.strategy_id)
    differences: list[dict[str, Any]] = []
    base_config = runtime.base_config

    for field_name in sorted(runtime.config_fields):
        if field_name in {"strategy_id", "strategy_name", "enabled"}:
            continue
        if field_name.startswith("live_"):
            continue
        if field_name not in candidate.param_dict:
            continue

        default_value = getattr(base_config, field_name)
        candidate_value = candidate.param_dict[field_name]
        if candidate_value != default_value:
            differences.append(
                {
                    "field": field_name,
                    "default_value": default_value,
                    "candidate_value": candidate_value,
                    "kind": "strategy_param",
                }
            )

    stop_loss = candidate.param_dict.get("stop_loss")
    take_profit = candidate.param_dict.get("take_profit")
    if hasattr(base_config, "live_stop_loss_price") and stop_loss is not None:
        default_stop = getattr(base_config, "live_stop_loss_price")
        if stop_loss != default_stop:
            differences.append(
                {
                    "field": "live_stop_loss_price",
                    "default_value": default_stop,
                    "candidate_value": stop_loss,
                    "kind": "exit_param",
                }
            )
    if hasattr(base_config, "live_take_profit_price") and take_profit is not None:
        default_take = getattr(base_config, "live_take_profit_price")
        if take_profit != default_take:
            differences.append(
                {
                    "field": "live_take_profit_price",
                    "default_value": default_take,
                    "candidate_value": take_profit,
                    "kind": "exit_param",
                }
            )

    return differences


def _accelerated_supported(strategy_id: str) -> bool:
    return strategy_id in {"S3", "S5"}


def prepare_accelerated_context(
    strategy_id: str,
    markets: list[dict],
) -> AcceleratedContext | None:
    """Prepare an accelerated validation context when supported."""
    if not _accelerated_supported(strategy_id):
        return None

    kernel = get_strategy_kernel(strategy_id)
    if kernel is None or not kernel.is_available():
        return None

    runtime = load_strategy_runtime(strategy_id)
    dataset = kernel.prepare(strategy_id=strategy_id, markets=markets, param_grid=runtime.param_grid)
    param_names = list(runtime.param_grid.keys())
    asset_labels = sorted({str(market["asset"]) for market in markets})
    asset_code_labels = {idx: label for idx, label in enumerate(asset_labels)}

    return AcceleratedContext(
        strategy_id=strategy_id,
        runtime=runtime,
        kernel=kernel,
        dataset=dataset,
        param_names=param_names,
        asset_code_labels=asset_code_labels,
    )


def _build_combo_tuple(param_names: list[str], param_dict: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(param_dict[name] for name in param_names)


def _run_candidate_accelerated(
    candidate: StrategyCandidate,
    markets: list[dict],
    *,
    slippage: float,
    context: AcceleratedContext | None = None,
) -> CandidateRun | None:
    """Run a candidate through the fast S3/S5 accelerator path."""
    if not _accelerated_supported(candidate.strategy_id):
        return None

    active_context = context
    if active_context is None:
        active_context = prepare_accelerated_context(candidate.strategy_id, markets)
    if active_context is None:
        return None

    combo = _build_combo_tuple(active_context.param_names, candidate.param_dict)
    encoded = active_context.kernel.encode_combo(combo)
    dataset = active_context.dataset
    dataset.slippage = slippage

    if candidate.strategy_id == "S3":
        payload = dataset.payload
        pnls, entry_fees, exit_fees, asset_codes, durations, market_indices = _evaluate_s3_combo(
            payload.common.prices,
            payload.common.total_seconds,
            payload.common.final_outcomes,
            payload.common.asset_codes,
            payload.common.duration_minutes,
            payload.common.fee_active,
            payload.nearest_prices[0],
            encoded,
            dataset.slippage,
        )
    elif candidate.strategy_id == "S5":
        payload = dataset.payload
        pnls, entry_fees, exit_fees, asset_codes, durations, market_indices = _evaluate_s5_combo(
            payload.common.prices,
            payload.common.total_seconds,
            payload.common.final_outcomes,
            payload.common.asset_codes,
            payload.common.duration_minutes,
            payload.common.fee_active,
            payload.common.hours,
            payload.nearest_prices,
            payload.encoded_hour_options,
            encoded,
            dataset.slippage,
        )
    else:
        return None

    metrics = compute_metrics_from_arrays(
        pnls,
        entry_fees,
        exit_fees,
        asset_codes,
        durations,
        config_id=candidate.label,
    )
    metrics["eligible_markets"] = dataset.eligible_markets
    metrics["skipped_markets_missing_features"] = dataset.skipped_markets_missing_features

    execution_stats = {
        "signals_seen": int(metrics.get("total_bets", 0)),
        "executed_trades": int(metrics.get("total_bets", 0)),
        "missed_delayed_entries": 0,
        "missed_end_of_market": 0,
        "missed_missing_price": 0,
    }

    eligible_market_ids = {market["market_id"] for market in markets}
    return CandidateRun(
        trades=[],
        metrics=metrics,
        eligible_market_ids=eligible_market_ids,
        skipped_markets_missing_features=dataset.skipped_markets_missing_features,
        execution_stats=execution_stats,
        pnls=pnls,
        entry_fees=entry_fees,
        exit_fees=exit_fees,
        asset_codes=asset_codes,
        duration_values=durations,
        trade_market_indices=market_indices,
        market_ids_by_index=[market["market_id"] for market in markets],
        asset_code_labels=active_context.asset_code_labels,
        accelerated=True,
    )


def _eligible_markets(strategy, markets: list[dict]) -> tuple[list[dict], set[str]]:
    eligible = [market for market in markets if strategy.market_is_eligible(market)]
    return eligible, {market["market_id"] for market in eligible}


def _metrics_with_context(
    trades: list,
    config_id: str,
    *,
    eligible_count: int,
    skipped_count: int,
) -> dict[str, Any]:
    metrics = compute_metrics(trades, config_id=config_id)
    metrics["eligible_markets"] = eligible_count
    metrics["skipped_markets_missing_features"] = skipped_count
    return metrics


def _run_strategy_with_entry_delay(
    config_id: str,
    strategy,
    markets: list[dict],
    *,
    slippage: float,
    entry_delay_seconds: int,
    entry_tolerance: int,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[list, dict[str, Any], set[str], int, dict[str, int]]:
    """Run a strategy with delayed entry execution."""
    eligible_markets, eligible_ids = _eligible_markets(strategy, markets)
    skipped_count = len(markets) - len(eligible_markets)

    trades: list = []
    execution_stats = {
        "signals_seen": 0,
        "executed_trades": 0,
        "missed_delayed_entries": 0,
        "missed_end_of_market": 0,
        "missed_missing_price": 0,
    }

    for market in eligible_markets:
        total_seconds = int(market["total_seconds"])
        for current_second in range(total_seconds):
            snapshot = market_to_snapshot(market, current_second)
            signal = strategy.evaluate(snapshot)
            if signal is None:
                continue

            intended_second = int(
                signal.signal_data.get(
                    "entry_second",
                    signal.signal_data.get("reversion_second", current_second),
                )
            )
            if intended_second != current_second:
                continue

            execution_stats["signals_seen"] += 1
            actual_entry_second = current_second + entry_delay_seconds
            if actual_entry_second >= total_seconds:
                execution_stats["missed_delayed_entries"] += 1
                execution_stats["missed_end_of_market"] += 1
                break

            delayed_up_price = get_price(
                market["prices"],
                actual_entry_second,
                tolerance=entry_tolerance,
            )
            if delayed_up_price is None:
                execution_stats["missed_delayed_entries"] += 1
                execution_stats["missed_missing_price"] += 1
                break

            delayed_entry_price = (
                delayed_up_price
                if signal.direction == "Up"
                else 1.0 - delayed_up_price
            )
            delayed_entry_price = max(0.01, min(0.99, delayed_entry_price))

            trades.append(
                make_trade(
                    market,
                    actual_entry_second,
                    delayed_entry_price,
                    signal.direction,
                    slippage=slippage,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            )
            execution_stats["executed_trades"] += 1
            break

    metrics = _metrics_with_context(
        trades,
        config_id,
        eligible_count=len(eligible_markets),
        skipped_count=skipped_count,
    )
    return trades, metrics, eligible_ids, skipped_count, execution_stats


def run_candidate(
    candidate: StrategyCandidate,
    markets: list[dict],
    *,
    slippage: float,
    entry_delay_seconds: int = 0,
    entry_tolerance: int = 2,
    accelerated_context: AcceleratedContext | None = None,
) -> CandidateRun:
    """Execute a fixed candidate against the provided market list."""
    if entry_delay_seconds <= 0:
        accelerated_run = _run_candidate_accelerated(
            candidate,
            markets,
            slippage=slippage,
            context=accelerated_context,
        )
        if accelerated_run is not None:
            return accelerated_run

    strategy, exit_params, _ = build_candidate(candidate)
    config_id = candidate.label

    if entry_delay_seconds <= 0:
        trades, metrics = run_strategy(
            config_id,
            strategy,
            markets,
            slippage=slippage,
            stop_loss=exit_params.get("stop_loss"),
            take_profit=exit_params.get("take_profit"),
            log_summary=False,
        )
        eligible_markets, eligible_ids = _eligible_markets(strategy, markets)
        execution_stats = {
            "signals_seen": int(metrics.get("total_bets", 0)),
            "executed_trades": int(metrics.get("total_bets", 0)),
            "missed_delayed_entries": 0,
            "missed_end_of_market": 0,
            "missed_missing_price": 0,
        }
        return CandidateRun(
            trades=trades,
            metrics=metrics,
            eligible_market_ids=eligible_ids,
            skipped_markets_missing_features=len(markets) - len(eligible_markets),
            execution_stats=execution_stats,
        )

    trades, metrics, eligible_ids, skipped_count, execution_stats = _run_strategy_with_entry_delay(
        config_id,
        strategy,
        markets,
        slippage=slippage,
        entry_delay_seconds=entry_delay_seconds,
        entry_tolerance=entry_tolerance,
        stop_loss=exit_params.get("stop_loss"),
        take_profit=exit_params.get("take_profit"),
    )
    return CandidateRun(
        trades=trades,
        metrics=metrics,
        eligible_market_ids=eligible_ids,
        skipped_markets_missing_features=skipped_count,
        execution_stats=execution_stats,
    )


def _market_sort_key(market: dict) -> datetime:
    return market.get("started_at") or datetime.min.replace(tzinfo=timezone.utc)


def _eligible_market_lookup(
    markets: list[dict],
    eligible_market_ids: set[str],
) -> tuple[dict[str, dict], list[dict]]:
    market_lookup = {market["market_id"]: market for market in markets}
    eligible_markets = [
        market_lookup[market_id]
        for market_id in eligible_market_ids
        if market_id in market_lookup
    ]
    eligible_markets.sort(key=_market_sort_key)
    return market_lookup, eligible_markets


def _empty_array(dtype=np.float64) -> np.ndarray:
    return np.array([], dtype=dtype)


def _slice_metrics_from_arrays(
    base_run: CandidateRun,
    config_id: str,
    market_ids: set[str],
    skipped_markets_missing_features: int = 0,
) -> dict[str, Any]:
    if (
        base_run.pnls is None
        or base_run.entry_fees is None
        or base_run.exit_fees is None
        or base_run.asset_codes is None
        or base_run.duration_values is None
        or base_run.trade_market_indices is None
        or base_run.market_ids_by_index is None
    ):
        return _metrics_with_context(
            [],
            config_id,
            eligible_count=len(market_ids),
            skipped_count=skipped_markets_missing_features,
        )

    allowed_indices = np.array(
        [
            index
            for index, market_id in enumerate(base_run.market_ids_by_index)
            if market_id in market_ids
        ],
        dtype=np.int64,
    )
    if allowed_indices.size == 0:
        pnls = _empty_array()
        entry_fees = _empty_array()
        exit_fees = _empty_array()
        asset_codes = np.array([], dtype=np.int64)
        duration_values = np.array([], dtype=np.int64)
    else:
        mask = np.isin(base_run.trade_market_indices, allowed_indices)
        pnls = base_run.pnls[mask]
        entry_fees = base_run.entry_fees[mask]
        exit_fees = base_run.exit_fees[mask]
        asset_codes = base_run.asset_codes[mask]
        duration_values = base_run.duration_values[mask]

    metrics = compute_metrics_from_arrays(
        pnls,
        entry_fees,
        exit_fees,
        asset_codes,
        duration_values,
        config_id=config_id,
    )
    metrics["eligible_markets"] = len(market_ids)
    metrics["skipped_markets_missing_features"] = skipped_markets_missing_features
    return metrics


def _slice_metrics(
    base_run: CandidateRun,
    config_id: str,
    market_ids: set[str],
    skipped_markets_missing_features: int = 0,
) -> dict[str, Any]:
    if base_run.accelerated:
        return _slice_metrics_from_arrays(
            base_run,
            config_id,
            market_ids,
            skipped_markets_missing_features=skipped_markets_missing_features,
        )

    filtered_trades = [trade for trade in base_run.trades if trade.market_id in market_ids]
    metrics = _metrics_with_context(
        filtered_trades,
        config_id,
        eligible_count=len(market_ids),
        skipped_count=skipped_markets_missing_features,
    )
    return metrics


def _chronological_fold_metrics(
    base_run: CandidateRun,
    markets: list[dict],
    *,
    folds: int,
) -> list[dict[str, Any]]:
    _, eligible_markets = _eligible_market_lookup(markets, base_run.eligible_market_ids)
    if not eligible_markets:
        return []

    fold_count = max(1, min(folds, len(eligible_markets)))
    split_markets = np.array_split(np.array(eligible_markets, dtype=object), fold_count)

    rows: list[dict[str, Any]] = []
    for idx, fold in enumerate(split_markets, 1):
        fold_list = list(fold)
        fold_ids = {market["market_id"] for market in fold_list}
        metrics = _slice_metrics(
            base_run,
            base_run.metrics["config_id"],
            fold_ids,
        )
        start_at = min((_market_sort_key(market) for market in fold_list), default=None)
        end_at = max((_market_sort_key(market) for market in fold_list), default=None)
        rows.append(
            {
                "fold": idx,
                "markets": len(fold_list),
                "start_at": start_at.isoformat() if start_at else None,
                "end_at": end_at.isoformat() if end_at else None,
                "metrics": metrics,
            }
        )
    return rows


def _group_market_ids(
    eligible_markets: list[dict],
    key_fn,
) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for market in eligible_markets:
        grouped[str(key_fn(market))].add(market["market_id"])
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _slice_breakdown(
    base_run: CandidateRun,
    markets: list[dict],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    _, eligible_markets = _eligible_market_lookup(markets, base_run.eligible_market_ids)
    if kind == "asset":
        grouped = _group_market_ids(eligible_markets, lambda market: market.get("asset", "unknown"))
    elif kind == "duration":
        grouped = _group_market_ids(
            eligible_markets,
            lambda market: f"{int(market.get('duration_minutes', 0))}m",
        )
    elif kind == "day":
        grouped = _group_market_ids(
            eligible_markets,
            lambda market: (market.get("started_at") or datetime.min.replace(tzinfo=timezone.utc)).date().isoformat(),
        )
    else:
        raise ValueError(f"Unsupported slice kind: {kind}")

    rows: list[dict[str, Any]] = []
    for label, market_ids in grouped.items():
        rows.append(
            {
                "label": label,
                "markets": len(market_ids),
                "metrics": _slice_metrics(
                    base_run,
                    base_run.metrics["config_id"],
                    market_ids,
                ),
            }
        )
    return rows


def _exit_reason_breakdown(trades: list) -> list[dict[str, Any]]:
    grouped: dict[str, list] = defaultdict(list)
    for trade in trades:
        grouped[getattr(trade, "exit_reason", "unknown")].append(trade)

    rows: list[dict[str, Any]] = []
    for reason, grouped_trades in sorted(grouped.items(), key=lambda item: item[0]):
        metrics = compute_metrics(grouped_trades, config_id=reason)
        rows.append(
            {
                "exit_reason": reason,
                "count": len(grouped_trades),
                "total_pnl": metrics["total_pnl"],
                "avg_bet_pnl": metrics["avg_bet_pnl"],
                "win_rate_pct": metrics["win_rate_pct"],
            }
        )
    return rows


def bootstrap_trade_pnl(
    trades: list,
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap trade-level PnL to estimate uncertainty."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    if not trades:
        return {
            "iterations": iterations,
            "probability_positive_pct": 0.0,
            "p05_total_pnl": 0.0,
            "p50_total_pnl": 0.0,
            "p95_total_pnl": 0.0,
            "mean_total_pnl": 0.0,
        }

    pnls = np.array([trade.pnl for trade in trades], dtype=float)
    rng = np.random.default_rng(seed)
    sampled = rng.choice(pnls, size=(iterations, len(pnls)), replace=True).sum(axis=1)

    return {
        "iterations": iterations,
        "probability_positive_pct": round(float(np.mean(sampled > 0.0) * 100.0), 2),
        "p05_total_pnl": round(float(np.percentile(sampled, 5)), 4),
        "p50_total_pnl": round(float(np.percentile(sampled, 50)), 4),
        "p95_total_pnl": round(float(np.percentile(sampled, 95)), 4),
        "mean_total_pnl": round(float(np.mean(sampled)), 4),
    }


def bootstrap_candidate_run(
    candidate_run: CandidateRun,
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap from a candidate run, supporting accelerated outputs."""
    if candidate_run.pnls is not None:
        if iterations < 1:
            raise ValueError("iterations must be >= 1")
        if candidate_run.pnls.size == 0:
            return {
                "iterations": iterations,
                "probability_positive_pct": 0.0,
                "p05_total_pnl": 0.0,
                "p50_total_pnl": 0.0,
                "p95_total_pnl": 0.0,
                "mean_total_pnl": 0.0,
            }

        rng = np.random.default_rng(seed)
        sampled = rng.choice(
            candidate_run.pnls,
            size=(iterations, len(candidate_run.pnls)),
            replace=True,
        ).sum(axis=1)
        return {
            "iterations": iterations,
            "probability_positive_pct": round(float(np.mean(sampled > 0.0) * 100.0), 2),
            "p05_total_pnl": round(float(np.percentile(sampled, 5)), 4),
            "p50_total_pnl": round(float(np.percentile(sampled, 50)), 4),
            "p95_total_pnl": round(float(np.percentile(sampled, 95)), 4),
            "mean_total_pnl": round(float(np.mean(sampled)), 4),
        }

    return bootstrap_trade_pnl(candidate_run.trades, iterations=iterations, seed=seed)


def _find_grid_index(value: Any, values: list[Any]) -> int | None:
    for idx, candidate_value in enumerate(values):
        if value == candidate_value:
            return idx
    return None


def evaluate_parameter_neighbors(
    candidate: StrategyCandidate,
    markets: list[dict],
    *,
    base_slippage: float,
    base_metrics: dict[str, Any],
    accelerated_context: AcceleratedContext | None = None,
) -> list[dict[str, Any]]:
    """Evaluate one-step parameter neighbors around the candidate."""
    runtime = load_strategy_runtime(candidate.strategy_id)
    rows: list[dict[str, Any]] = []

    for param_name, values in runtime.param_grid.items():
        if param_name not in candidate.param_dict:
            continue

        current_index = _find_grid_index(candidate.param_dict[param_name], values)
        if current_index is None:
            continue

        for offset, direction in ((-1, "lower"), (1, "higher")):
            neighbor_index = current_index + offset
            if neighbor_index < 0 or neighbor_index >= len(values):
                continue

            neighbor_params = dict(candidate.param_dict)
            neighbor_params[param_name] = values[neighbor_index]
            neighbor = StrategyCandidate(
                strategy_id=candidate.strategy_id,
                param_dict=neighbor_params,
                source_label=f"neighbor:{param_name}:{direction}",
            )
            run = run_candidate(
                neighbor,
                markets,
                slippage=base_slippage,
                accelerated_context=accelerated_context,
            )
            rows.append(
                {
                    "parameter": param_name,
                    "direction": direction,
                    "candidate_value": candidate.param_dict[param_name],
                    "neighbor_value": values[neighbor_index],
                    "total_bets": run.metrics["total_bets"],
                    "total_pnl": run.metrics["total_pnl"],
                    "profit_factor": run.metrics["profit_factor"],
                    "sharpe_ratio": run.metrics["sharpe_ratio"],
                    "delta_total_pnl": round(
                        float(run.metrics["total_pnl"] - base_metrics["total_pnl"]),
                        4,
                    ),
                    "delta_profit_factor": round(
                        float(run.metrics["profit_factor"] - base_metrics["profit_factor"]),
                        4,
                    ),
                    "delta_sharpe_ratio": round(
                        float(run.metrics["sharpe_ratio"] - base_metrics["sharpe_ratio"]),
                        4,
                    ),
                }
            )

    rows.sort(
        key=lambda row: (
            -abs(row["delta_total_pnl"]),
            row["parameter"],
            row["direction"],
        )
    )
    return rows


def _dataset_summary(markets: list[dict], eligible_market_ids: set[str]) -> dict[str, Any]:
    eligible_lookup = {
        market["market_id"]: market
        for market in markets
        if market["market_id"] in eligible_market_ids
    }
    assets: dict[str, int] = defaultdict(int)
    durations: dict[str, int] = defaultdict(int)
    days: dict[str, int] = defaultdict(int)
    for market in eligible_lookup.values():
        assets[str(market.get("asset", "unknown"))] += 1
        durations[f"{int(market.get('duration_minutes', 0))}m"] += 1
        day_key = (
            market.get("started_at") or datetime.min.replace(tzinfo=timezone.utc)
        ).date().isoformat()
        days[day_key] += 1

    started = [_market_sort_key(market) for market in eligible_lookup.values()]
    return {
        "total_markets": len(markets),
        "eligible_markets": len(eligible_lookup),
        "assets": dict(sorted(assets.items())),
        "durations": dict(sorted(durations.items())),
        "days": dict(sorted(days.items())),
        "date_range_start": min(started).isoformat() if started else None,
        "date_range_end": max(started).isoformat() if started else None,
    }


def run_validation_suite(
    candidate: StrategyCandidate,
    markets: list[dict],
    *,
    base_slippage: float = 0.01,
    slippage_grid: tuple[float, ...] = DEFAULT_SLIPPAGE_GRID,
    entry_delays: tuple[int, ...] = DEFAULT_ENTRY_DELAYS,
    chronological_folds: int = DEFAULT_FOLD_COUNT,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    include_neighbors: bool = True,
) -> dict[str, Any]:
    """Run the full validation suite for a fixed strategy candidate."""
    if not markets:
        raise ValueError("markets must not be empty")

    accelerated_context = prepare_accelerated_context(candidate.strategy_id, markets)
    base_run = run_candidate(
        candidate,
        markets,
        slippage=base_slippage,
        accelerated_context=accelerated_context,
    )
    results: dict[str, Any] = {
        "generated_at": _now_utc_iso(),
        "candidate": {
            "strategy_id": candidate.strategy_id,
            "config_id": candidate.config_id,
            "label": candidate.label,
            "rank": candidate.rank,
            "source_label": candidate.source_label,
            "param_dict": candidate.param_dict,
        },
        "dataset": _dataset_summary(markets, base_run.eligible_market_ids),
        "default_drift": compare_candidate_to_defaults(candidate),
        "overall": {
            "base_slippage": base_slippage,
            "accelerated": base_run.accelerated,
            "metrics": base_run.metrics,
            "execution_stats": base_run.execution_stats,
        },
        "slippage_sweep": [],
        "entry_delay_sweep": [],
        "chronological_folds": _chronological_fold_metrics(
            base_run,
            markets,
            folds=chronological_folds,
        ),
        "asset_slices": _slice_breakdown(base_run, markets, kind="asset"),
        "duration_slices": _slice_breakdown(base_run, markets, kind="duration"),
        "day_slices": _slice_breakdown(base_run, markets, kind="day"),
        "exit_reason_breakdown": [] if base_run.accelerated else _exit_reason_breakdown(base_run.trades),
        "bootstrap": bootstrap_candidate_run(
            base_run,
            iterations=bootstrap_iterations,
        ),
        "parameter_neighbors": [],
    }

    seen_slippages = set()
    for slippage in slippage_grid:
        if slippage in seen_slippages:
            continue
        seen_slippages.add(slippage)
        if slippage == base_slippage:
            run = base_run
        else:
            run = run_candidate(
                candidate,
                markets,
                slippage=slippage,
                accelerated_context=accelerated_context,
            )
        results["slippage_sweep"].append(
            {
                "slippage": slippage,
                "metrics": run.metrics,
                "execution_stats": run.execution_stats,
            }
        )

    seen_delays = set()
    for delay in entry_delays:
        if delay in seen_delays:
            continue
        seen_delays.add(delay)
        if delay == 0:
            run = base_run
        else:
            run = run_candidate(
                candidate,
                markets,
                slippage=base_slippage,
                entry_delay_seconds=delay,
                accelerated_context=accelerated_context,
            )
        results["entry_delay_sweep"].append(
            {
                "entry_delay_seconds": delay,
                "metrics": run.metrics,
                "execution_stats": run.execution_stats,
            }
        )

    if include_neighbors:
        results["parameter_neighbors"] = evaluate_parameter_neighbors(
            candidate,
            markets,
            base_slippage=base_slippage,
            base_metrics=base_run.metrics,
            accelerated_context=accelerated_context,
        )

    return results


def _md_table(columns: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def render_validation_markdown(results: dict[str, Any]) -> str:
    """Render validation results as Markdown."""
    candidate = results["candidate"]
    overall = results["overall"]["metrics"]
    accelerated = bool(results["overall"].get("accelerated"))
    drift = results["default_drift"]
    lines = [
        f"# Validation: {candidate['label']}",
        "",
        f"- Generated at: {results['generated_at']}",
        f"- Strategy: {candidate['strategy_id']}",
        f"- Source: {candidate.get('source_label') or 'manual'}",
        "",
        "## Overall",
        "",
        _md_table(
            ["Metric", "Value"],
            [
                ["total_bets", overall["total_bets"]],
                ["win_rate_pct", overall["win_rate_pct"]],
                ["total_pnl", overall["total_pnl"]],
                ["profit_factor", overall["profit_factor"]],
                ["sharpe_ratio", overall["sharpe_ratio"]],
                ["max_drawdown", overall["max_drawdown"]],
                ["eligible_markets", overall["eligible_markets"]],
                ["accelerated", accelerated],
                [
                    "skipped_markets_missing_features",
                    overall["skipped_markets_missing_features"],
                ],
            ],
        ),
        "",
        "## Candidate Parameters",
        "",
        _md_table(
            ["Parameter", "Value"],
            [[key, value] for key, value in candidate["param_dict"].items()],
        ),
        "",
        "## Default Drift",
        "",
    ]

    if drift:
        lines.extend(
            [
                _md_table(
                    ["Field", "Kind", "Default", "Candidate"],
                    [
                        [
                            row["field"],
                            row["kind"],
                            row["default_value"],
                            row["candidate_value"],
                        ]
                        for row in drift
                    ],
                ),
                "",
            ]
        )
    else:
        lines.extend(["No drift from default/live configuration.", ""])

    lines.extend(
        [
            "## Slippage Sweep",
            "",
            _md_table(
                ["Slippage", "Bets", "PnL", "PF", "Sharpe", "MaxDD"],
                [
                    [
                        row["slippage"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                        row["metrics"]["max_drawdown"],
                    ]
                    for row in results["slippage_sweep"]
                ],
            ),
            "",
            "## Entry Delay Sweep",
            "",
            _md_table(
                ["Delay(s)", "Bets", "PnL", "PF", "Sharpe", "MissedEntries"],
                [
                    [
                        row["entry_delay_seconds"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                        row["execution_stats"]["missed_delayed_entries"],
                    ]
                    for row in results["entry_delay_sweep"]
                ],
            ),
            "",
            "## Chronological Folds",
            "",
            _md_table(
                ["Fold", "Markets", "Bets", "PnL", "PF", "Sharpe", "Start", "End"],
                [
                    [
                        row["fold"],
                        row["markets"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                        row["start_at"],
                        row["end_at"],
                    ]
                    for row in results["chronological_folds"]
                ],
            ),
            "",
            "## Asset Slices",
            "",
            _md_table(
                ["Asset", "Markets", "Bets", "PnL", "PF", "Sharpe"],
                [
                    [
                        row["label"],
                        row["markets"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                    ]
                    for row in results["asset_slices"]
                ],
            ),
            "",
            "## Duration Slices",
            "",
            _md_table(
                ["Duration", "Markets", "Bets", "PnL", "PF", "Sharpe"],
                [
                    [
                        row["label"],
                        row["markets"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                    ]
                    for row in results["duration_slices"]
                ],
            ),
            "",
            "## Day Slices",
            "",
            _md_table(
                ["Day", "Markets", "Bets", "PnL", "PF", "Sharpe"],
                [
                    [
                        row["label"],
                        row["markets"],
                        row["metrics"]["total_bets"],
                        row["metrics"]["total_pnl"],
                        row["metrics"]["profit_factor"],
                        row["metrics"]["sharpe_ratio"],
                    ]
                    for row in results["day_slices"]
                ],
            ),
            "",
            "## Exit Reasons",
            "",
        ]
    )

    if results["exit_reason_breakdown"]:
        lines.extend(
            [
                _md_table(
                    ["ExitReason", "Count", "PnL", "AvgPnL", "WinRate%"],
                    [
                        [
                            row["exit_reason"],
                            row["count"],
                            row["total_pnl"],
                            row["avg_bet_pnl"],
                            row["win_rate_pct"],
                        ]
                        for row in results["exit_reason_breakdown"]
                    ],
                ),
                "",
            ]
        )
    elif accelerated:
        lines.extend(
            [
                "Exit reasons are omitted in accelerated mode to keep validation fast.",
                "",
            ]
        )
    else:
        lines.extend(["No exits recorded.", ""])

    lines.extend(
        [
            "## Bootstrap Robustness",
            "",
            _md_table(
                ["Metric", "Value"],
                [[key, value] for key, value in results["bootstrap"].items()],
            ),
            "",
        ]
    )

    if results["parameter_neighbors"]:
        lines.extend(
            [
                "## Parameter Neighbors",
                "",
                _md_table(
                    [
                        "Parameter",
                        "Direction",
                        "Candidate",
                        "Neighbor",
                        "PnL",
                        "DeltaPnL",
                        "PF",
                        "Sharpe",
                    ],
                    [
                        [
                            row["parameter"],
                            row["direction"],
                            row["candidate_value"],
                            row["neighbor_value"],
                            row["total_pnl"],
                            row["delta_total_pnl"],
                            row["profit_factor"],
                            row["sharpe_ratio"],
                        ]
                        for row in results["parameter_neighbors"][:20]
                    ],
                ),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def save_validation_results(
    results: dict[str, Any],
    output_dir: str | Path,
    basename: str,
) -> tuple[Path, Path]:
    """Save JSON and Markdown validation outputs."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_path = output_path / f"{basename}.json"
    md_path = output_path / f"{basename}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
        handle.write("\n")

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(render_validation_markdown(results))

    return json_path, md_path
