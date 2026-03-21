"""CLI wrapper for validating a fixed shared-strategy candidate."""

from __future__ import annotations

import argparse
import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.backtest import data_loader
from analysis.validation import (
    StrategyCandidate,
    candidate_from_results_csv,
    load_strategy_runtime,
    run_validation_suite,
    save_validation_results,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _candidate_from_config(strategy_id: str, source: str) -> StrategyCandidate:
    runtime = load_strategy_runtime(strategy_id)
    config_module = importlib.import_module(f"shared.strategies.{strategy_id}.config")

    if source == "candidate" and hasattr(config_module, "get_candidate_config"):
        config = config_module.get_candidate_config()
        source_label = f"{strategy_id}:candidate"
    elif source == "baseline" and hasattr(config_module, "get_baseline_config"):
        config = config_module.get_baseline_config()
        source_label = f"{strategy_id}:baseline"
    else:
        config = config_module.get_default_config()
        source_label = f"{strategy_id}:default"

    param_dict: dict[str, Any] = {}
    missing: list[str] = []
    for param_name in runtime.param_grid:
        if hasattr(config, param_name):
            param_dict[param_name] = getattr(config, param_name)
            continue
        if param_name == "stop_loss" and hasattr(config, "live_stop_loss_price"):
            param_dict[param_name] = getattr(config, "live_stop_loss_price")
            continue
        if param_name == "take_profit" and hasattr(config, "live_take_profit_price"):
            param_dict[param_name] = getattr(config, "live_take_profit_price")
            continue
        missing.append(param_name)

    if missing:
        raise ValueError(
            f"Config source '{source_label}' does not expose parameters: {missing}"
        )

    return StrategyCandidate(
        strategy_id=strategy_id,
        param_dict=param_dict,
        source_label=source_label,
    )


def _parse_assets(raw_assets: str | None) -> list[str] | None:
    if not raw_assets:
        return None
    return [asset.strip().lower() for asset in raw_assets.split(",") if asset.strip()]


def _parse_durations(raw_durations: str | None) -> list[int] | None:
    if not raw_durations:
        return None
    return [int(duration.strip()) for duration in raw_durations.split(",") if duration.strip()]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="analysis.validate_candidate",
        description="Validate a fixed shared-strategy candidate with deeper robustness checks.",
    )
    parser.add_argument("--strategy", required=True, help="Strategy ID, for example S13.")
    parser.add_argument(
        "--candidate-source",
        choices=("candidate", "default", "baseline", "csv"),
        default="candidate",
        help="How to load the candidate config (default: candidate).",
    )
    parser.add_argument(
        "--csv-path",
        default=None,
        help="Optimizer CSV to read when --candidate-source=csv.",
    )
    parser.add_argument(
        "--rank",
        type=int,
        default=1,
        help="1-based CSV rank to load when --candidate-source=csv (default: 1).",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset filter, for example BTC,ETH,SOL,XRP.",
    )
    parser.add_argument(
        "--durations",
        default=None,
        help="Comma-separated duration filter in minutes, for example 5,15.",
    )
    parser.add_argument(
        "--base-slippage",
        type=float,
        default=0.01,
        help="Base slippage for the main validation run (default: 0.01).",
    )
    parser.add_argument(
        "--folds",
        type=int,
        default=4,
        help="Chronological fold count (default: 4).",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=300,
        help="Bootstrap iterations for robustness estimates (default: 300).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for validation outputs. Defaults to ./results/validation/<strategy>/run_<timestamp>.",
    )
    args = parser.parse_args(argv)

    if args.candidate_source == "csv":
        if not args.csv_path:
            raise SystemExit("--csv-path is required when --candidate-source=csv")
        candidate = candidate_from_results_csv(args.strategy, args.csv_path, rank=args.rank)
    else:
        candidate = _candidate_from_config(args.strategy, args.candidate_source)

    print(f"Loading market data for {args.strategy}...")
    markets = data_loader.load_all_data()
    if not markets:
        raise SystemExit("No markets loaded.")

    assets = _parse_assets(args.assets)
    durations = _parse_durations(args.durations)
    if assets or durations:
        markets = data_loader.filter_markets(markets, assets=assets, durations=durations)
        print(f"After filtering: {len(markets)} markets")
    if not markets:
        raise SystemExit("No markets remain after applying filters.")

    results = run_validation_suite(
        candidate,
        markets,
        base_slippage=args.base_slippage,
        chronological_folds=args.folds,
        bootstrap_iterations=args.bootstrap_iterations,
        include_neighbors=True,
    )

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = f"./results/validation/{args.strategy}/run_{_timestamp()}"

    json_path, md_path = save_validation_results(
        results,
        output_dir,
        basename=f"validate_{args.strategy}_{args.candidate_source}",
    )

    overall = results["overall"]["metrics"]
    print("\n=== Validation Summary ===")
    print(f"Candidate: {candidate.label}")
    print(f"Trades: {overall['total_bets']}")
    print(f"Win rate: {overall['win_rate_pct']:.2f}%")
    print(f"Total PnL: {overall['total_pnl']:.4f}")
    print(f"Avg bet PnL: {overall['avg_bet_pnl']:.6f}")
    print(f"Profit factor: {overall['profit_factor']:.4f}")
    print(f"Sharpe: {overall['sharpe_ratio']:.4f}")
    print(f"Max drawdown: {overall['max_drawdown']:.4f}")
    print(f"Saved JSON: {Path(json_path).resolve()}")
    print(f"Saved Markdown: {Path(md_path).resolve()}")


if __name__ == "__main__":
    main()
