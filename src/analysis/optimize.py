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
import dataclasses
import importlib
import itertools
import math
import sys

import pandas as pd

from analysis.backtest_strategies import run_strategy
from analysis.backtest.engine import (
    Trade,
    add_ranking_score,
    save_module_results,
)
from shared.strategies.registry import discover_strategies


# ── Core optimizer ──────────────────────────────────────────────────


def optimize_strategy(
    strategy_id: str,
    markets: list[dict] | None,
    output_dir: str,
    dry_run: bool = False,
) -> pd.DataFrame | None:
    """Run grid-search optimization for a single strategy.

    Parameters
    ----------
    strategy_id:
        Registry ID (e.g. ``'S1'``).
    markets:
        List of market dicts from ``data_loader``.  May be ``None`` when
        *dry_run* is ``True``.
    output_dir:
        Directory where results CSVs/analysis are written.
    dry_run:
        If ``True``, print the grid summary and return without backtesting.

    Returns
    -------
    DataFrame of ranked results, or ``None`` if dry-run / skipped.
    """
    # ── Validate strategy ───────────────────────────────────────────
    registry = discover_strategies()

    if strategy_id not in registry:
        available = sorted(registry.keys())
        print(f"ERROR: Strategy '{strategy_id}' not found. Available: {available}")
        sys.exit(1)

    if strategy_id == "TEMPLATE":
        print("ERROR: Cannot optimize TEMPLATE strategy — it is a skeleton only.")
        sys.exit(1)

    # ── Import param grid ───────────────────────────────────────────
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

    # ── Print grid summary ──────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Grid-Search Optimization: {strategy_id}")
    print(f"{'='*60}")
    print(f"\nParameters ({len(param_names)}):")
    for name, values in grid.items():
        print(f"  {name}: {values}")
    print(f"\nTotal combinations: {total_combos}")

    if dry_run:
        # Verify param split logic during dry-run
        base_config = config_module.get_default_config()
        config_fields = {f.name for f in dataclasses.fields(type(base_config))}
        exit_param_names = [name for name in param_names if name not in config_fields]
        
        if exit_param_names:
            print(f"\nExit parameters (not in config dataclass): {exit_param_names}")
        
        print("\n[dry-run] Exiting without running backtests.")
        return None

    # ── Run backtests ───────────────────────────────────────────────
    if markets is None:
        print("ERROR: No market data provided for non-dry-run.")
        sys.exit(1)

    strategy_cls = registry[strategy_id]
    get_default_config = config_module.get_default_config
    base_config = get_default_config()

    # Introspect config dataclass to identify valid fields
    config_fields = {f.name for f in dataclasses.fields(type(base_config))}

    all_metrics: list[dict] = []
    trades_by_config: dict[str, list[Trade]] = {}

    print(f"\nRunning {total_combos} backtests...\n")

    for i, combo in enumerate(itertools.product(*param_values), 1):
        param_dict = dict(zip(param_names, combo))

        # Split param_dict into strategy params and exit params
        strategy_params = {k: v for k, v in param_dict.items() if k in config_fields}
        exit_params = {k: v for k, v in param_dict.items() if k not in config_fields}

        # Build descriptive config label
        param_parts = [f"{k}={v}" for k, v in param_dict.items()]
        config_label = f"{strategy_id}_{'_'.join(param_parts)}"

        # Create config with overridden params (strategy params only)
        custom_config = dataclasses.replace(base_config, **strategy_params)

        # Instantiate strategy with custom config
        strategy = strategy_cls(custom_config)

        # Run backtest with exit params threaded through
        print(f"  [{i}/{total_combos}] {config_label}")
        trades, metrics = run_strategy(
            config_label,
            strategy,
            markets,
            stop_loss=exit_params.get('stop_loss'),
            take_profit=exit_params.get('take_profit'),
        )

        all_metrics.append(metrics)
        trades_by_config[config_label] = trades

    # ── Rank and save ───────────────────────────────────────────────
    df = pd.DataFrame(all_metrics)
    df = add_ranking_score(df)
    df = df.sort_values("ranking_score", ascending=False).reset_index(drop=True)

    # Print top 10 summary
    print(f"\n{'='*60}")
    print(f"Top Results for {strategy_id} ({total_combos} combinations)")
    print(f"{'='*60}\n")

    top_n = min(10, len(df))
    for idx, row in df.head(top_n).iterrows():
        print(
            f"  #{idx+1}: {row['config_id']}\n"
            f"       Bets={row['total_bets']}, "
            f"WR={row['win_rate_pct']:.1f}%, "
            f"PnL={row['total_pnl']:.4f}, "
            f"Sharpe={row['sharpe_ratio']:.3f}, "
            f"Score={row['ranking_score']:.1f}, "
            f"SL={row.get('stop_loss', 'N/A')}, "
            f"TP={row.get('take_profit', 'N/A')}"
        )

    # Save results
    module_name = f"optimize_{strategy_id}"
    save_module_results(df, trades_by_config, module_name, output_dir)
    print(f"\nResults saved to {output_dir}/")

    return df


# ── CLI ─────────────────────────────────────────────────────────────


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
    args = parser.parse_args(argv)

    # ── Load market data (skip for dry-run) ─────────────────────────
    markets = None
    if not args.dry_run:
        from analysis.backtest import data_loader

        print("Loading market data...")
        markets = data_loader.load_all_data()
        if not markets:
            print("No markets loaded. Exiting.")
            sys.exit(1)

        # Apply filters
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

    # ── Run optimizer ───────────────────────────────────────────────
    optimize_strategy(
        strategy_id=args.strategy,
        markets=markets,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
