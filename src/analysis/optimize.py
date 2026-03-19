"""Grid-search parameter optimizer for shared strategies."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import importlib
import itertools
import math
import multiprocessing
import os
import sys
from datetime import datetime, timezone
from collections.abc import Iterable, Iterator

import numpy as np
import pandas as pd

from analysis.accelerators import get_strategy_kernel, has_strategy_kernel
from analysis.backtest.engine import Trade, add_ranking_score, save_module_results
from analysis.backtest_strategies import run_strategy
from shared.strategies.registry import discover_strategies


_GENERIC_WORKER_CONTEXT: dict[str, object] = {}
_ACCEL_WORKER_CONTEXT: dict[str, object] = {}


def _build_config_label(strategy_id: str, param_dict: dict[str, object]) -> str:
    param_parts = [f"{k}={v}" for k, v in param_dict.items()]
    return f"{strategy_id}_{'_'.join(param_parts)}"


def _load_strategy_grid(strategy_id: str) -> tuple[dict[str, type], object, dict[str, list], list[str], list[list]]:
    registry = discover_strategies()
    if strategy_id not in registry:
        available = sorted(registry.keys())
        print(f"ERROR: Strategy '{strategy_id}' not found. Available: {available}")
        sys.exit(1)

    if strategy_id == "TEMPLATE":
        print("ERROR: Cannot optimize TEMPLATE strategy — it is a skeleton only.")
        sys.exit(1)

    config_module = importlib.import_module(f"shared.strategies.{strategy_id}.config")
    if not hasattr(config_module, "get_param_grid"):
        print(f"Strategy {strategy_id} has no get_param_grid() — skipping.")
        sys.exit(1)

    grid = config_module.get_param_grid()
    if not grid:
        print(f"Strategy {strategy_id} get_param_grid() returned empty dict — skipping.")
        sys.exit(1)

    param_names = list(grid.keys())
    param_values = list(grid.values())
    return registry, config_module, grid, param_names, param_values


def _print_grid_summary(strategy_id: str, grid: dict[str, list], config_fields: set[str], dry_run: bool) -> int:
    total_combos = math.prod(len(values) for values in grid.values())
    print(f"\n{'=' * 60}")
    print(f"Grid-Search Optimization: {strategy_id}")
    print(f"{'=' * 60}")
    print(f"\nParameters ({len(grid)}):")
    for name, values in grid.items():
        print(f"  {name}: {values}")
    print(f"\nTotal combinations: {total_combos}")

    if dry_run:
        exit_param_names = [name for name in grid if name not in config_fields]
        if exit_param_names:
            print(f"\nExit parameters (not in config dataclass): {exit_param_names}")
        print("\n[dry-run] Exiting without running backtests.")
    return total_combos


def _init_generic_worker(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
) -> None:
    global _GENERIC_WORKER_CONTEXT
    _GENERIC_WORKER_CONTEXT = {
        "strategy_id": strategy_id,
        "strategy_cls": strategy_cls,
        "base_config": base_config,
        "config_fields": config_fields,
        "markets": markets,
        "param_names": param_names,
    }


def _evaluate_generic_combo(combo: tuple[object, ...]) -> dict:
    strategy_id = _GENERIC_WORKER_CONTEXT["strategy_id"]
    strategy_cls = _GENERIC_WORKER_CONTEXT["strategy_cls"]
    base_config = _GENERIC_WORKER_CONTEXT["base_config"]
    config_fields = _GENERIC_WORKER_CONTEXT["config_fields"]
    markets = _GENERIC_WORKER_CONTEXT["markets"]
    param_names = _GENERIC_WORKER_CONTEXT["param_names"]

    param_dict = dict(zip(param_names, combo))
    strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}
    exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}

    config_label = _build_config_label(strategy_id, param_dict)
    custom_config = dataclasses.replace(base_config, **strategy_params)
    strategy = strategy_cls(custom_config)

    _, metrics = run_strategy(
        config_label,
        strategy,
        markets,
        stop_loss=exit_params.get("stop_loss"),
        take_profit=exit_params.get("take_profit"),
        log_summary=False,
    )
    metrics.update(param_dict)
    return metrics


def _iter_generic_metrics(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
    param_values: list[list[object]],
    workers: int,
    total_combos: int,
    progress_interval: int,
) -> list[dict]:
    all_metrics: list[dict] = []

    if workers <= 1:
        _init_generic_worker(
            strategy_id,
            strategy_cls,
            base_config,
            config_fields,
            markets,
            param_names,
        )
        for completed, combo in enumerate(itertools.product(*param_values), 1):
            all_metrics.append(_evaluate_generic_combo(combo))
            if completed % progress_interval == 0 or completed == total_combos:
                print(f"  Completed {completed}/{total_combos} combinations")
        return all_metrics

    mp_context = multiprocessing.get_context("fork") if os.name != "nt" else None
    chunksize = max(1, min(100, total_combos // max(workers * 20, 1) or 1))
    combo_iter = itertools.product(*param_values)

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=mp_context,
        initializer=_init_generic_worker,
        initargs=(
            strategy_id,
            strategy_cls,
            base_config,
            config_fields,
            markets,
            param_names,
        ),
    ) as executor:
        for completed, metrics in enumerate(
            executor.map(_evaluate_generic_combo, combo_iter, chunksize=chunksize),
            1,
        ):
            all_metrics.append(metrics)
            if completed % progress_interval == 0 or completed == total_combos:
                print(f"  Completed {completed}/{total_combos} combinations")

    return all_metrics


def _init_accel_worker(strategy_id: str, dataset, param_names: list[str]) -> None:
    global _ACCEL_WORKER_CONTEXT
    _ACCEL_WORKER_CONTEXT = {
        "strategy_id": strategy_id,
        "kernel": get_strategy_kernel(strategy_id),
        "dataset": dataset,
        "param_names": param_names,
    }


def _iter_combo_batches(
    kernel,
    param_values: list[list[object]],
    batch_size: int,
) -> Iterator[tuple[np.ndarray, list[tuple[object, ...]]]]:
    combo_batch: list[tuple[object, ...]] = []
    encoded_batch: list[np.ndarray] = []

    for combo in itertools.product(*param_values):
        combo_batch.append(combo)
        encoded_batch.append(kernel.encode_combo(combo))
        if len(combo_batch) >= batch_size:
            yield np.vstack(encoded_batch), combo_batch
            combo_batch = []
            encoded_batch = []

    if combo_batch:
        yield np.vstack(encoded_batch), combo_batch


def _evaluate_accel_batch(batch: tuple[np.ndarray, list[tuple[object, ...]]]) -> list[dict]:
    encoded_batch, combo_batch = batch
    kernel = _ACCEL_WORKER_CONTEXT["kernel"]
    dataset = _ACCEL_WORKER_CONTEXT["dataset"]
    param_names = _ACCEL_WORKER_CONTEXT["param_names"]
    strategy_id = _ACCEL_WORKER_CONTEXT["strategy_id"]
    return kernel.evaluate_batch(
        dataset=dataset,
        encoded_batch=encoded_batch,
        combo_batch=combo_batch,
        param_names=param_names,
        config_id_builder=_build_config_label,
    )


def _iter_accelerated_metrics(
    strategy_id: str,
    dataset,
    kernel,
    param_names: list[str],
    param_values: list[list[object]],
    workers: int,
    total_combos: int,
    progress_interval: int,
) -> list[dict]:
    all_metrics: list[dict] = []
    processed = 0
    batch_size = max(128, min(2048, total_combos // max(workers * 8, 1) or 128))

    if workers <= 1:
        _init_accel_worker(strategy_id, dataset, param_names)
        for batch in _iter_combo_batches(kernel, param_values, batch_size):
            batch_metrics = _evaluate_accel_batch(batch)
            all_metrics.extend(batch_metrics)
            processed += len(batch_metrics)
            while processed and (
                processed % progress_interval == 0
                or processed == total_combos
                or (processed > total_combos - progress_interval and processed < total_combos)
            ):
                print(f"  Completed {min(processed, total_combos)}/{total_combos} combinations")
                break
        return all_metrics

    mp_context = multiprocessing.get_context("fork") if os.name != "nt" else None
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=mp_context,
        initializer=_init_accel_worker,
        initargs=(strategy_id, dataset, param_names),
    ) as executor:
        batches = _iter_combo_batches(kernel, param_values, batch_size)
        for batch_metrics in executor.map(_evaluate_accel_batch, batches, chunksize=1):
            all_metrics.extend(batch_metrics)
            processed += len(batch_metrics)
            if (
                processed % progress_interval == 0
                or processed >= total_combos
                or processed > total_combos - progress_interval
            ):
                print(f"  Completed {min(processed, total_combos)}/{total_combos} combinations")

    return all_metrics


def _rerun_top_configs_for_trades(
    df: pd.DataFrame,
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
    top_n: int = 10,
) -> dict[str, list[Trade]]:
    trades_by_config: dict[str, list[Trade]] = {}

    for _, row in df.head(top_n).iterrows():
        param_dict = {name: row[name] for name in param_names if name in row.index}
        strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}
        exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}
        config_label = _build_config_label(strategy_id, param_dict)
        custom_config = dataclasses.replace(base_config, **strategy_params)
        strategy = strategy_cls(custom_config)
        trades, _ = run_strategy(
            config_label,
            strategy,
            markets,
            stop_loss=exit_params.get("stop_loss"),
            take_profit=exit_params.get("take_profit"),
            log_summary=False,
        )
        trades_by_config[config_label] = trades

    return trades_by_config


def _materialize_top_trades_accelerated(
    df: pd.DataFrame,
    strategy_id: str,
    kernel,
    dataset,
    param_names: list[str],
    top_n: int = 10,
) -> dict[str, list[Trade]]:
    trades_by_config: dict[str, list[Trade]] = {}
    for _, row in df.head(top_n).iterrows():
        param_dict = {name: row[name] for name in param_names if name in row.index}
        config_label = _build_config_label(strategy_id, param_dict)
        trades_by_config[config_label] = kernel.materialize_trades(dataset, param_dict, config_label)
    return trades_by_config


def _print_top_results(strategy_id: str, total_combos: int, df: pd.DataFrame) -> None:
    print(f"\n{'=' * 60}")
    print(f"Top Results for {strategy_id} ({total_combos} combinations)")
    print(f"{'=' * 60}\n")

    top_n = min(10, len(df))
    for idx, row in df.head(top_n).iterrows():
        print(
            f"  #{idx + 1}: {row['config_id']}\n"
            f"       Bets={row['total_bets']}, "
            f"WR={row['win_rate_pct']:.1f}%, "
            f"PnL={row['total_pnl']:.4f}, "
            f"Sharpe={row['sharpe_ratio']:.3f}, "
            f"Score={row['ranking_score']:.1f}, "
            f"SL={row.get('stop_loss', 'N/A')}, "
            f"TP={row.get('take_profit', 'N/A')}"
        )


def _build_s1_run_output_dir(base_output_dir: str, strategy_id: str) -> str:
    """Create a unique per-run directory for S1 optimization outputs."""
    strategy_root = os.path.join(base_output_dir, strategy_id)
    os.makedirs(strategy_root, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    candidate = os.path.join(strategy_root, timestamp)
    suffix = 1
    while os.path.exists(candidate):
        candidate = os.path.join(strategy_root, f"{timestamp}_{suffix:02d}")
        suffix += 1

    os.makedirs(candidate, exist_ok=False)
    return candidate


def optimize_strategy(
    strategy_id: str,
    markets: list[dict] | None,
    output_dir: str,
    dry_run: bool = False,
    workers: int = 1,
    progress_interval: int = 100,
    engine: str = "auto",
) -> pd.DataFrame | None:
    registry, config_module, grid, param_names, param_values = _load_strategy_grid(strategy_id)
    base_config = config_module.get_default_config()
    config_fields = {f.name for f in dataclasses.fields(type(base_config))}
    kernel = get_strategy_kernel(strategy_id)

    if engine == "accelerated":
        if kernel is None:
            print(f"ERROR: Strategy {strategy_id} has no accelerated kernel.")
            sys.exit(1)
        if not kernel.is_available():
            print(f"ERROR: Accelerated engine unavailable for {strategy_id}: {kernel.unavailable_reason()}")
            sys.exit(1)

    total_combos = _print_grid_summary(strategy_id, grid, config_fields, dry_run)
    if dry_run:
        return None

    if markets is None:
        print("ERROR: No market data provided for non-dry-run.")
        sys.exit(1)

    resolved_engine = engine
    if engine == "auto":
        if kernel is not None and kernel.is_available():
            resolved_engine = "accelerated"
        else:
            resolved_engine = "generic"

    print(f"\nRunning {total_combos} backtests...\n")
    print(f"Engine: {resolved_engine}")
    print(f"Using {workers} worker process(es)")
    print(f"Progress log interval: every {progress_interval} combinations")

    strategy_cls = registry[strategy_id]

    if resolved_engine == "generic":
        all_metrics = _iter_generic_metrics(
            strategy_id=strategy_id,
            strategy_cls=strategy_cls,
            base_config=base_config,
            config_fields=config_fields,
            markets=markets,
            param_names=param_names,
            param_values=param_values,
            workers=workers,
            total_combos=total_combos,
            progress_interval=progress_interval,
        )
        df = pd.DataFrame(all_metrics)
        df = add_ranking_score(df)
        df = df.sort_values("ranking_score", ascending=False).reset_index(drop=True)
        print("\nRe-running top 10 configurations to capture sample trades...")
        trades_by_config = _rerun_top_configs_for_trades(
            df=df,
            strategy_id=strategy_id,
            strategy_cls=strategy_cls,
            base_config=base_config,
            config_fields=config_fields,
            markets=markets,
            param_names=param_names,
            top_n=10,
        )
    else:
        assert kernel is not None
        dataset = kernel.prepare(strategy_id=strategy_id, markets=markets, param_grid=grid)
        all_metrics = _iter_accelerated_metrics(
            strategy_id=strategy_id,
            dataset=dataset,
            kernel=kernel,
            param_names=param_names,
            param_values=param_values,
            workers=workers,
            total_combos=total_combos,
            progress_interval=progress_interval,
        )
        df = pd.DataFrame(all_metrics)
        df = add_ranking_score(df)
        df = df.sort_values("ranking_score", ascending=False).reset_index(drop=True)
        print("\nRe-running top 10 configurations to capture sample trades...")
        trades_by_config = _materialize_top_trades_accelerated(
            df=df,
            strategy_id=strategy_id,
            kernel=kernel,
            dataset=dataset,
            param_names=param_names,
            top_n=10,
        )

    _print_top_results(strategy_id, total_combos, df)

    resolved_output_dir = output_dir
    if strategy_id == "S1":
        resolved_output_dir = _build_s1_run_output_dir(output_dir, strategy_id)

    module_name = f"optimize_{strategy_id}"
    save_module_results(df, trades_by_config, module_name, resolved_output_dir)
    print(f"\nResults saved to {resolved_output_dir}/")
    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="analysis.optimize",
        description="Grid-search parameter optimizer for shared strategies.",
    )
    parser.add_argument("--strategy", required=True, help="Strategy ID to optimize (e.g. S1, S2).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print grid summary and exit without running backtests.",
    )
    parser.add_argument(
        "--output-dir",
        default="./results/optimization",
        help="Directory for results (default: ./results/optimization).",
    )
    parser.add_argument("--assets", default=None, help="Comma-separated asset filter (e.g. BTC,ETH).")
    parser.add_argument(
        "--durations",
        default=None,
        help="Comma-separated duration filter in minutes (e.g. 5,15).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) - 1),
        help="Worker processes for parallel evaluation (default: CPU count - 1).",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "generic", "accelerated"),
        default="auto",
        help="Optimization engine selection (default: auto).",
    )
    args = parser.parse_args(argv)

    markets = None
    if not args.dry_run:
        from analysis.backtest import data_loader

        print("Loading market data...")
        markets = data_loader.load_all_data()
        if not markets:
            print("No markets loaded. Exiting.")
            sys.exit(1)

        asset_list = args.assets.split(",") if args.assets else None
        duration_list = [int(d) for d in args.durations.split(",")] if args.durations else None
        if asset_list or duration_list:
            markets = data_loader.filter_markets(markets, assets=asset_list, durations=duration_list)
            print(f"After filtering: {len(markets)} markets")

    optimize_strategy(
        strategy_id=args.strategy,
        markets=markets,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        workers=max(1, args.workers),
        progress_interval=100,
        engine=args.engine,
    )


if __name__ == "__main__":
    main()
