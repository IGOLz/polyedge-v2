"""Grid-search parameter optimizer for shared strategies.

Systematically explores a strategy's config space by generating the Cartesian
product of parameter values defined in each strategy's ``get_param_grid()``,
backtests every combination via the existing engine, and ranks results.

Usage::

    # Dry run — print grid summary without loading market data
    cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run

    # Full optimization run
    cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S1

    # With asset/duration filters
    cd src && PYTHONPATH=. python3 -m analysis.optimize --strategy S2 --assets BTC,ETH --durations 5
"""

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

import pandas as pd

from analysis.backtest.engine import Trade, add_ranking_score, save_module_results
from analysis.backtest_strategies import run_strategy
from shared.strategies.registry import discover_strategies


_WORKER_CONTEXT: dict[str, object] = {}


def _init_worker(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
) -> None:
    """Store shared optimization state inside each worker process."""
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = {
        "strategy_id": strategy_id,
        "strategy_cls": strategy_cls,
        "base_config": base_config,
        "config_fields": config_fields,
        "markets": markets,
        "param_names": param_names,
    }


def _build_config_label(strategy_id: str, param_dict: dict[str, object]) -> str:
    param_parts = [f"{k}={v}" for k, v in param_dict.items()]
    return f"{strategy_id}_{'_'.join(param_parts)}"


def _evaluate_combo(combo: tuple[object, ...]) -> tuple[dict, list[Trade]]:
    """Evaluate one parameter combination using the shared worker context."""
    strategy_id = _WORKER_CONTEXT["strategy_id"]
    strategy_cls = _WORKER_CONTEXT["strategy_cls"]
    base_config = _WORKER_CONTEXT["base_config"]
    config_fields = _WORKER_CONTEXT["config_fields"]
    markets = _WORKER_CONTEXT["markets"]
    param_names = _WORKER_CONTEXT["param_names"]

    param_dict = dict(zip(param_names, combo))
    strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}
    exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}

    config_label = _build_config_label(strategy_id, param_dict)
    custom_config = dataclasses.replace(base_config, **strategy_params)
    strategy = strategy_cls(custom_config)

    trades, metrics = run_strategy(
        config_label,
        strategy,
        markets,
        stop_loss=exit_params.get("stop_loss"),
        take_profit=exit_params.get("take_profit"),
        log_summary=False,
    )
    metrics.update(param_dict)
    return metrics, trades


def _iter_metrics_parallel(
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
    """Evaluate combinations across worker processes and return metrics only."""
    all_metrics: list[dict] = []

    mp_context = None
    if os.name != "nt":
        mp_context = multiprocessing.get_context("fork")

    chunksize = max(1, min(100, total_combos // max(workers * 20, 1) or 1))
    combo_iter = itertools.product(*param_values)

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=mp_context,
        initializer=_init_worker,
        initargs=(
            strategy_id,
            strategy_cls,
            base_config,
            config_fields,
            markets,
            param_names,
        ),
    ) as executor:
        for completed, (metrics, _) in enumerate(
            executor.map(_evaluate_combo, combo_iter, chunksize=chunksize),
            1,
        ):
            all_metrics.append(metrics)
            if completed % progress_interval == 0 or completed == total_combos:
                print(f"  Completed {completed}/{total_combos} combinations")

    return all_metrics


def _iter_metrics_serial(
    strategy_id: str,
    strategy_cls,
    base_config,
    config_fields: set[str],
    markets: list[dict],
    param_names: list[str],
    param_values: list[list[object]],
    total_combos: int,
    progress_interval: int,
) -> list[dict]:
    """Evaluate combinations in a single process and return metrics only."""
    _init_worker(
        strategy_id,
        strategy_cls,
        base_config,
        config_fields,
        markets,
        param_names,
    )

    all_metrics: list[dict] = []
    for completed, combo in enumerate(itertools.product(*param_values), 1):
        metrics, _ = _evaluate_combo(combo)
        all_metrics.append(metrics)
        if completed % progress_interval == 0 or completed == total_combos:
            print(f"  Completed {completed}/{total_combos} combinations")

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
    """Rerun only the top configurations to capture sample trades for reports."""
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


def optimize_strategy(
    strategy_id: str,
    markets: list[dict] | None,
    output_dir: str,
    dry_run: bool = False,
    workers: int = 1,
    progress_interval: int = 100,
) -> pd.DataFrame | None:
    """Run grid-search optimization for a single strategy."""
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
        return None

    grid = config_module.get_param_grid()
    if not grid:
        print(f"Strategy {strategy_id} get_param_grid() returned empty dict — skipping.")
        return None

    param_names = list(grid.keys())
    param_values = list(grid.values())
    total_combos = math.prod(len(values) for values in param_values)

    print(f"\n{'='*60}")
    print(f"Grid-Search Optimization: {strategy_id}")
    print(f"{'='*60}")
    print(f"\nParameters ({len(param_names)}):")
    for name, values in grid.items():
        print(f"  {name}: {values}")
    print(f"\nTotal combinations: {total_combos}")

    base_config = config_module.get_default_config()
    config_fields = {f.name for f in dataclasses.fields(type(base_config))}

    if dry_run:
        exit_param_names = [name for name in param_names if name not in config_fields]
        if exit_param_names:
            print(f"\nExit parameters (not in config dataclass): {exit_param_names}")
        print("\n[dry-run] Exiting without running backtests.")
        return None

    if markets is None:
        print("ERROR: No market data provided for non-dry-run.")
        sys.exit(1)

    strategy_cls = registry[strategy_id]

    print(f"\nRunning {total_combos} backtests...\n")
    print(f"Using {workers} worker process(es)")
    print(f"Progress log interval: every {progress_interval} combinations")

    if workers > 1:
        all_metrics = _iter_metrics_parallel(
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
    else:
        all_metrics = _iter_metrics_serial(
            strategy_id=strategy_id,
            strategy_cls=strategy_cls,
            base_config=base_config,
            config_fields=config_fields,
            markets=markets,
            param_names=param_names,
            param_values=param_values,
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

    print(f"\n{'='*60}")
    print(f"Top Results for {strategy_id} ({total_combos} combinations)")
    print(f"{'='*60}\n")

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

    module_name = f"optimize_{strategy_id}"
    save_module_results(df, trades_by_config, module_name, output_dir)
    print(f"\nResults saved to {output_dir}/")

    return df


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``python3 -m analysis.optimize``."""
    parser = argparse.ArgumentParser(
        prog="analysis.optimize",
        description="Grid-search parameter optimizer for shared strategies.",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy ID to optimize (e.g. S1, S2).",
    )
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
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset filter (e.g. BTC,ETH).",
    )
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
        duration_list = (
            [int(d) for d in args.durations.split(",")]
            if args.durations
            else None
        )
        if asset_list or duration_list:
            markets = data_loader.filter_markets(
                markets, assets=asset_list, durations=duration_list
            )
            print(f"After filtering: {len(markets)} markets")

    optimize_strategy(
        strategy_id=args.strategy,
        markets=markets,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        workers=max(1, args.workers),
        progress_interval=100,
    )


if __name__ == "__main__":
    main()
