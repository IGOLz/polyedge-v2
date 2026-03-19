#!/usr/bin/env python3
"""Run deep validation for fixed strategy candidates.

Examples:
    cd src && PYTHONPATH=. python scripts/validate_candidate.py \
        --strategy S5 \
        --results-csv results/optimization/S5/run_20260319_204940/Test_optimize_S5_Results.csv \
        --rank 1

    cd src && PYTHONPATH=. python scripts/validate_candidate.py \
        --strategy S3 \
        --config-json "{\"spike_threshold\": 0.78, \"spike_lookback\": 30, ... }"
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from analysis.backtest import data_loader
from analysis.validation import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_ENTRY_DELAYS,
    DEFAULT_FOLD_COUNT,
    DEFAULT_SLIPPAGE_GRID,
    StrategyCandidate,
    candidate_from_results_csv,
    run_validation_suite,
    save_validation_results,
)


def _parse_float_tuple(raw: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in raw.split(",") if part.strip())


def _parse_int_tuple(raw: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


def _build_output_dir(base_output_dir: str, strategy_id: str) -> Path:
    strategy_root = Path(base_output_dir) / strategy_id
    strategy_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    candidate = strategy_root / timestamp
    suffix = 1
    while candidate.exists():
        candidate = strategy_root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _parse_config_object(raw: str):
    text = raw.strip()
    candidates = [text]

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        candidates.append(text[1:-1].strip())

    normalized = re.sub(r'([{\s,])([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    if normalized != text:
        candidates.append(normalized)
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
            candidates.append(normalized[1:-1].strip())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)

        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(candidate)
            except (json.JSONDecodeError, ValueError, SyntaxError):
                continue

            if isinstance(value, str) and value.strip() != candidate:
                nested = _parse_config_object(value)
                if isinstance(nested, dict):
                    return nested
            if isinstance(value, dict):
                return value

    raise SystemExit("--config-json must be valid JSON or a Python-style dict literal.")


def _load_candidates(args) -> list[StrategyCandidate]:
    if args.results_csv:
        if args.top_n is not None:
            return [
                candidate_from_results_csv(args.strategy, args.results_csv, rank=rank)
                for rank in range(1, args.top_n + 1)
            ]
        return [
            candidate_from_results_csv(args.strategy, args.results_csv, rank=args.rank)
        ]

    param_dict = _parse_config_object(args.config_json)

    return [
        StrategyCandidate(
            strategy_id=args.strategy,
            param_dict=param_dict,
            source_label="manual-json",
        )
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="scripts.validate_candidate",
        description="Run deep validation for one or more fixed strategy candidates.",
    )
    parser.add_argument("--strategy", required=True, help="Strategy ID (for example S3 or S5).")

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--results-csv",
        help="Optimizer CSV to load candidate rows from.",
    )
    source_group.add_argument(
        "--config-json",
        help="Manual candidate params as JSON.",
    )

    parser.add_argument(
        "--rank",
        type=int,
        default=1,
        help="1-based rank to validate from --results-csv (default: 1).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Validate ranks 1..N from --results-csv.",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Optional comma-separated asset filter (for example BTC,ETH).",
    )
    parser.add_argument(
        "--durations",
        default=None,
        help="Optional comma-separated duration filter in minutes (for example 5,15).",
    )
    parser.add_argument(
        "--base-slippage",
        type=float,
        default=0.01,
        help="Base slippage for the main validation run (default: 0.01).",
    )
    parser.add_argument(
        "--slippages",
        default=",".join(str(value) for value in DEFAULT_SLIPPAGE_GRID),
        help="Comma-separated slippage sweep values (default: 0.0,0.01,0.02,0.03).",
    )
    parser.add_argument(
        "--entry-delays",
        default=",".join(str(value) for value in DEFAULT_ENTRY_DELAYS),
        help="Comma-separated entry delay sweep in seconds (default: 0). Nonzero delays use the slower exact path.",
    )
    parser.add_argument(
        "--folds",
        type=int,
        default=DEFAULT_FOLD_COUNT,
        help=f"Chronological fold count (default: {DEFAULT_FOLD_COUNT}).",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=DEFAULT_BOOTSTRAP_ITERATIONS,
        help=f"Bootstrap iterations (default: {DEFAULT_BOOTSTRAP_ITERATIONS}).",
    )
    parser.add_argument(
        "--skip-neighbors",
        action="store_true",
        help="Skip one-step parameter neighbor validation.",
    )
    parser.add_argument(
        "--output-dir",
        default="./results/validation",
        help="Directory for validation outputs (default: ./results/validation).",
    )
    args = parser.parse_args(argv)

    print("Loading market data...")
    markets = data_loader.load_all_data()
    if not markets:
        raise SystemExit("No markets loaded.")

    asset_list = (
        [asset.strip().lower() for asset in args.assets.split(",") if asset.strip()]
        if args.assets
        else None
    )
    duration_list = (
        [int(duration.strip()) for duration in args.durations.split(",") if duration.strip()]
        if args.durations
        else None
    )
    if asset_list or duration_list:
        markets = data_loader.filter_markets(
            markets,
            assets=asset_list,
            durations=duration_list,
        )
        print(f"After filtering: {len(markets)} markets")

    candidates = _load_candidates(args)
    output_dir = _build_output_dir(args.output_dir, args.strategy)
    entry_delays = _parse_int_tuple(args.entry_delays)

    if any(delay > 0 for delay in entry_delays):
        print("Note: nonzero entry delays use the slower exact execution path.")

    print(f"Validating {len(candidates)} candidate(s)...")
    for index, candidate in enumerate(candidates, 1):
        print(f"  [{index}/{len(candidates)}] {candidate.label}")
        results = run_validation_suite(
            candidate,
            markets,
            base_slippage=args.base_slippage,
            slippage_grid=_parse_float_tuple(args.slippages),
            entry_delays=entry_delays,
            chronological_folds=max(1, args.folds),
            bootstrap_iterations=max(1, args.bootstrap_iterations),
            include_neighbors=not args.skip_neighbors,
        )
        basename = f"candidate_{index:02d}"
        json_path, md_path = save_validation_results(results, output_dir, basename)
        overall = results["overall"]["metrics"]
        bootstrap = results["bootstrap"]
        print(
            "    "
            f"bets={overall['total_bets']} "
            f"pnl={overall['total_pnl']} "
            f"pf={overall['profit_factor']} "
            f"sharpe={overall['sharpe_ratio']} "
            f"bootstrap_pos={bootstrap['probability_positive_pct']}%"
        )
        print(f"    saved {json_path}")
        print(f"    saved {md_path}")

    print(f"Validation outputs saved to {output_dir}")


if __name__ == "__main__":
    main()
