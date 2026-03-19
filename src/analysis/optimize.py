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
import time
from datetime import datetime, timezone
from collections.abc import Iterator

import numpy as np
import pandas as pd

from analysis.accelerators import get_strategy_kernel, has_strategy_kernel
from analysis.backtest.engine import add_ranking_score, save_module_results
from analysis.backtest_strategies import run_strategy
from analysis.constants import DEFAULT_ENTRY_SLIPPAGE
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


def _format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _print_progress_update(completed: int, total: int, start_time: float) -> None:
    elapsed = max(0.001, time.monotonic() - start_time)
    rate = completed / elapsed
    remaining = max(0, total - completed)
    eta_seconds = remaining / rate if rate > 0 else 0.0
    print(
        "  "
        f"Completed {completed}/{total} combinations "
        f"| elapsed {_format_elapsed(elapsed)} "
        f"| rate {rate:.2f}/s "
        f"| eta {_format_elapsed(eta_seconds)}"
    )


def _init_generic_worker(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
    slippage: float,
) -> None:
    global _GENERIC_WORKER_CONTEXT
    _GENERIC_WORKER_CONTEXT = {
        "strategy_id": strategy_id,
        "strategy_cls": strategy_cls,
        "base_config": base_config,
        "config_fields": config_fields,
        "markets": markets,
        "param_names": param_names,
        "slippage": slippage,
    }


def _evaluate_generic_combo(combo: tuple[object, ...]) -> dict:
    strategy_id = _GENERIC_WORKER_CONTEXT["strategy_id"]
    strategy_cls = _GENERIC_WORKER_CONTEXT["strategy_cls"]
    base_config = _GENERIC_WORKER_CONTEXT["base_config"]
    config_fields = _GENERIC_WORKER_CONTEXT["config_fields"]
    markets = _GENERIC_WORKER_CONTEXT["markets"]
    param_names = _GENERIC_WORKER_CONTEXT["param_names"]
    slippage = _GENERIC_WORKER_CONTEXT["slippage"]

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
        slippage=slippage,
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
    slippage: float,
) -> list[dict]:
    all_metrics: list[dict] = []
    start_time = time.monotonic()

    if workers <= 1:
        print("  Running generic optimization in a single process.")
        _init_generic_worker(
            strategy_id,
            strategy_cls,
            base_config,
            config_fields,
            markets,
            param_names,
            slippage,
        )
        for completed, combo in enumerate(itertools.product(*param_values), 1):
            all_metrics.append(_evaluate_generic_combo(combo))
            if (
                completed == 1
                or completed % progress_interval == 0
                or completed == total_combos
            ):
                _print_progress_update(completed, total_combos, start_time)
        return all_metrics

    mp_context = multiprocessing.get_context("fork") if os.name != "nt" else None
    combo_iter = iter(itertools.product(*param_values))
    max_in_flight = max(workers * 4, 1)

    print(f"  Launching {workers} generic worker processes...")
    if os.name == "nt":
        print(
            "  Windows generic mode copies market data into fresh worker processes. "
            "The first completion can take a while."
        )

    def _submit_initial_work(executor, futures: dict[concurrent.futures.Future, None]) -> int:
        submitted = 0
        while len(futures) < max_in_flight:
            try:
                combo = next(combo_iter)
            except StopIteration:
                break
            futures[executor.submit(_evaluate_generic_combo, combo)] = None
            submitted += 1
        return submitted

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
            slippage,
        ),
    ) as executor:
        futures: dict[concurrent.futures.Future, None] = {}
        submitted = _submit_initial_work(executor, futures)
        print(f"  Submitted {submitted}/{total_combos} combinations to worker queue")
        print("  Waiting for first completed combination...")

        completed = 0
        while futures:
            done, _ = concurrent.futures.wait(
                futures,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                futures.pop(future)
                all_metrics.append(future.result())
                completed += 1

                if (
                    completed == 1
                    or completed % progress_interval == 0
                    or completed == total_combos
                ):
                    _print_progress_update(completed, total_combos, start_time)

                while len(futures) < max_in_flight:
                    try:
                        combo = next(combo_iter)
                    except StopIteration:
                        break
                    futures[executor.submit(_evaluate_generic_combo, combo)] = None

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


def _build_strategy_run_output_dir(base_output_dir: str, strategy_id: str) -> str:
    """Create a unique per-run directory for a strategy's optimization outputs."""
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


def _materialize_config_result(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    param_names: list[str],
    row: pd.Series,
    markets: list[dict],
    slippage: float,
) -> tuple[list, dict]:
    param_dict = {name: row[name] for name in param_names}
    strategy_params = {key: value for key, value in param_dict.items() if key in config_fields}
    exit_params = {key: value for key, value in param_dict.items() if key not in config_fields}
    strategy = strategy_cls(dataclasses.replace(base_config, **strategy_params))
    return run_strategy(
        str(row["config_id"]),
        strategy,
        markets,
        slippage=slippage,
        stop_loss=exit_params.get("stop_loss"),
        take_profit=exit_params.get("take_profit"),
        log_summary=False,
    )


def _write_validation_report(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    param_names: list[str],
    markets: list[dict],
    df: pd.DataFrame,
    output_dir: str,
    slippage: float,
    top_n: int = 3,
) -> None:
    if df.empty or not markets:
        return

    market_day = {
        market["market_id"]: market["started_at"].date().isoformat()
        for market in markets
        if market.get("started_at") is not None
    }
    sorted_markets = sorted(
        markets,
        key=lambda market: market.get("started_at") or datetime.min.replace(tzinfo=timezone.utc),
    )
    fold_count = min(4, len(sorted_markets))
    folds = [list(fold) for fold in np.array_split(np.array(sorted_markets, dtype=object), fold_count) if len(fold) > 0]

    report_path = os.path.join(output_dir, f"optimize_{strategy_id}_Validation.md")
    lines = [
        f"# optimize_{strategy_id} Validation",
        "",
        f"- Default slippage used: {slippage:.2f}",
        f"- Validation configs analyzed: {min(top_n, len(df))}",
        f"- Chronological folds: {len(folds)}",
        "",
    ]

    for rank, (_, row) in enumerate(df.head(top_n).iterrows(), 1):
        trades, metrics = _materialize_config_result(
            strategy_id,
            strategy_cls,
            base_config,
            config_fields,
            param_names,
            row,
            markets,
            slippage,
        )
        lines.append(f"## Rank {rank}: {row['config_id']}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key in ("total_bets", "win_rate_pct", "total_pnl", "profit_factor", "sharpe_ratio", "max_drawdown"):
            lines.append(f"| {key} | {metrics.get(key, 0)} |")
        lines.append("")

        asset_totals: dict[str, float] = {}
        duration_totals: dict[int, float] = {}
        day_totals: dict[str, float] = {}
        for trade in trades:
            asset_totals[trade.asset] = asset_totals.get(trade.asset, 0.0) + trade.pnl
            duration_totals[trade.duration_minutes] = duration_totals.get(trade.duration_minutes, 0.0) + trade.pnl
            trade_day = market_day.get(trade.market_id)
            if trade_day is not None:
                day_totals[trade_day] = day_totals.get(trade_day, 0.0) + trade.pnl

        if asset_totals:
            lines.append("### Asset Breakdown")
            lines.append("")
            lines.append("| Asset | Total PnL |")
            lines.append("|-------|-----------|")
            for asset, pnl in sorted(asset_totals.items()):
                lines.append(f"| {asset.upper()} | {pnl:.4f} |")
            lines.append("")

        if duration_totals:
            lines.append("### Duration Breakdown")
            lines.append("")
            lines.append("| Duration | Total PnL |")
            lines.append("|----------|-----------|")
            for duration, pnl in sorted(duration_totals.items()):
                lines.append(f"| {duration}m | {pnl:.4f} |")
            lines.append("")

        if day_totals:
            profitable_days = sum(1 for pnl in day_totals.values() if pnl > 0)
            worst_day = min(day_totals.items(), key=lambda item: item[1])
            best_day = max(day_totals.items(), key=lambda item: item[1])
            lines.append("### Daily Robustness")
            lines.append("")
            lines.append(f"- Profitable days: {profitable_days}/{len(day_totals)}")
            lines.append(f"- Best day: {best_day[0]} ({best_day[1]:+.4f})")
            lines.append(f"- Worst day: {worst_day[0]} ({worst_day[1]:+.4f})")
            lines.append("")

        if folds:
            lines.append("### Chronological Folds")
            lines.append("")
            lines.append("| Fold | Markets | Bets | Win Rate % | Total PnL | Profit Factor |")
            lines.append("|------|---------|------------|------------|-----------|---------------|")
            for fold_idx, fold_markets in enumerate(folds, 1):
                _, fold_metrics = _materialize_config_result(
                    strategy_id,
                    strategy_cls,
                    base_config,
                    config_fields,
                    param_names,
                    row,
                    fold_markets,
                    slippage,
                )
                lines.append(
                    "| "
                    f"{fold_idx} | {len(fold_markets)} | {fold_metrics.get('total_bets', 0)} | "
                    f"{fold_metrics.get('win_rate_pct', 0):.2f} | {fold_metrics.get('total_pnl', 0):.4f} | "
                    f"{fold_metrics.get('profit_factor', 0):.4f} |"
                )
            lines.append("")

    with open(report_path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"  Saved {report_path}")


def optimize_strategy(
    strategy_id: str,
    markets: list[dict] | None,
    output_dir: str,
    dry_run: bool = False,
    workers: int = 1,
    progress_interval: int = 100,
    engine: str = "auto",
    slippage: float = DEFAULT_ENTRY_SLIPPAGE,
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
    print(f"Entry slippage: {slippage:.2f}")

    if resolved_engine == "generic":
        all_metrics = _iter_generic_metrics(
            strategy_id=strategy_id,
            strategy_cls=registry[strategy_id],
            base_config=base_config,
            config_fields=config_fields,
            markets=markets,
            param_names=param_names,
            param_values=param_values,
            workers=workers,
            total_combos=total_combos,
            progress_interval=progress_interval,
            slippage=slippage,
        )
        df = pd.DataFrame(all_metrics)
        df = add_ranking_score(df)
        df = df.sort_values("ranking_score", ascending=False).reset_index(drop=True)
    else:
        assert kernel is not None
        dataset = kernel.prepare(strategy_id=strategy_id, markets=markets, param_grid=grid)
        dataset.slippage = slippage
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

    _print_top_results(strategy_id, total_combos, df)

    resolved_output_dir = _build_strategy_run_output_dir(output_dir, strategy_id)

    module_name = f"optimize_{strategy_id}"
    save_module_results(df, {}, module_name, resolved_output_dir)
    _write_validation_report(
        strategy_id=strategy_id,
        strategy_cls=registry[strategy_id],
        base_config=base_config,
        config_fields=config_fields,
        param_names=param_names,
        markets=markets,
        df=df,
        output_dir=resolved_output_dir,
        slippage=slippage,
    )
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
        "--progress-interval",
        type=int,
        default=25,
        help="Print progress after this many completed combinations (default: 25).",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "generic", "accelerated"),
        default="auto",
        help="Optimization engine selection (default: auto).",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=DEFAULT_ENTRY_SLIPPAGE,
        help=(
            "Entry slippage penalty in price units "
            f"(default: {DEFAULT_ENTRY_SLIPPAGE:.2f})."
        ),
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
        progress_interval=max(1, args.progress_interval),
        engine=args.engine,
        slippage=args.slippage,
    )


if __name__ == "__main__":
    main()
