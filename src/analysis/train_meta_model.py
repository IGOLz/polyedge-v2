"""Train and evaluate a tree-based selector on expert-signal opportunities."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.backtest import data_loader
from analysis.meta_tree import (
    ExpectedPnlTreeRegressor,
    TabularFeatureEncoder,
    apply_selection_policy,
    choose_prediction_threshold,
    compute_signal_metrics,
)
from analysis.opportunity_dataset import (
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_DURATIONS,
    DEFAULT_EXPERTS,
    build_dataset_summary,
    build_opportunity_dataset,
)
from analysis.walkforward import apply_walkforward_split, build_embargoed_walkforward_splits


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")


def _parse_csv_list(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [value.strip() for value in raw.split(",") if value.strip()]


def _parse_duration_list(raw: str | None) -> list[int] | None:
    values = _parse_csv_list(raw)
    if values is None:
        return None
    return [int(value) for value in values]


def _default_output_dir() -> Path:
    return Path("./results/meta_model") / _timestamp()


def _experts_from_dataset(dataset: pd.DataFrame) -> list[str]:
    if "strategy_id" not in dataset.columns:
        return []
    return sorted(str(value) for value in dataset["strategy_id"].dropna().unique())


def _policy_comparison(selector_metrics: dict[str, Any], baseline_metrics: dict[str, Any]) -> dict[str, float]:
    selector_bets = float(selector_metrics["total_bets"])
    baseline_bets = float(baseline_metrics["total_bets"])
    selector_pnl = float(selector_metrics["total_pnl"])
    baseline_pnl = float(baseline_metrics["total_pnl"])
    return {
        "trade_retain_pct": round(selector_bets / baseline_bets * 100.0, 2) if baseline_bets else 0.0,
        "pnl_retain_pct": round(selector_pnl / baseline_pnl * 100.0, 2) if baseline_pnl else 0.0,
        "pnl_delta": round(selector_pnl - baseline_pnl, 4),
        "profit_factor_delta": round(
            float(selector_metrics["profit_factor"]) - float(baseline_metrics["profit_factor"]),
            4,
        ),
        "sharpe_delta": round(
            float(selector_metrics["sharpe_ratio"]) - float(baseline_metrics["sharpe_ratio"]),
            4,
        ),
        "max_drawdown_delta": round(
            float(selector_metrics["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
            4,
        ),
    }


def _build_deployment_artifact(
    dataset: pd.DataFrame,
    prediction_frame: pd.DataFrame,
    *,
    max_depth: int,
    min_samples_leaf: int,
    min_validation_trades: int,
    min_threshold: float,
    top_k_per_day: int | None,
    top_percent_per_day: float | None,
) -> dict[str, Any]:
    baseline_oos_metrics = compute_signal_metrics(
        prediction_frame,
        config_id="all_signals_pooled_oos",
    )
    pooled_threshold, pooled_oos_metrics, pooled_leaderboard = choose_prediction_threshold(
        prediction_frame,
        prediction_frame["predicted_pnl"].to_numpy(dtype=float, copy=False),
        min_trades=min_validation_trades,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )
    pooled_selected, pooled_policy_summary = apply_selection_policy(
        prediction_frame,
        threshold=pooled_threshold,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )
    pooled_selector_metrics = compute_signal_metrics(
        pooled_selected,
        config_id="selector_pooled_oos",
    )

    encoder = TabularFeatureEncoder()
    full_x = encoder.fit_transform(dataset)
    model = ExpectedPnlTreeRegressor(
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )
    model.fit(full_x, dataset["realized_pnl"].to_numpy(dtype=float, copy=False))

    full_predictions = dataset.copy()
    full_predictions["predicted_pnl"] = model.predict(full_x)
    full_predictions["predicted_positive_rate"] = model.predict_positive_rate(full_x)
    full_selected, full_policy_summary = apply_selection_policy(
        full_predictions,
        threshold=pooled_threshold,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )
    full_selector_metrics = compute_signal_metrics(
        full_selected,
        config_id="selector_full_sample",
    )
    full_baseline_metrics = compute_signal_metrics(
        dataset,
        config_id="all_signals_full_sample",
    )

    return {
        "recommended_threshold": float(pooled_threshold),
        "policy": {
            "min_threshold": float(min_threshold),
            "top_k_per_day": top_k_per_day,
            "top_percent_per_day": top_percent_per_day,
        },
        "pooled_oos_metrics": pooled_oos_metrics,
        "pooled_oos_policy_summary": pooled_policy_summary,
        "pooled_oos_selector_metrics": pooled_selector_metrics,
        "pooled_oos_baseline_metrics": baseline_oos_metrics,
        "pooled_oos_comparison": _policy_comparison(
            pooled_selector_metrics,
            baseline_oos_metrics,
        ),
        "full_sample_selector_metrics": full_selector_metrics,
        "full_sample_baseline_metrics": full_baseline_metrics,
        "full_sample_comparison": _policy_comparison(
            full_selector_metrics,
            full_baseline_metrics,
        ),
        "full_sample_policy_summary": full_policy_summary,
        "threshold_leaderboard_top5": pooled_leaderboard[:5],
        "encoder": encoder.to_payload(),
        "model": model.to_payload(feature_names=encoder.feature_names_),
    }


def _render_markdown(results: dict[str, Any]) -> str:
    overall = results["overall"]
    policy = results["policy"]
    retained = overall["comparison"]
    deployment = results.get("deployment")
    lines = [
        "# Meta-Model Selector",
        "",
        "## Summary",
        "",
        f"- Dataset rows: {results['dataset']['rows']}",
        f"- Dataset markets: {results['dataset']['markets']}",
        f"- Experts: {', '.join(results['experts'])}",
        f"- Splits: {len(results['splits'])}",
        f"- Min threshold: {policy['min_threshold']:.6f}",
        f"- Top K per day: {policy['top_k_per_day'] if policy['top_k_per_day'] is not None else 'off'}",
        f"- Top percent per day: {policy['top_percent_per_day'] if policy['top_percent_per_day'] is not None else 'off'}",
        "",
        "## Overall Test Metrics",
        "",
        "| Metric | Selector | All Signals |",
        "| --- | --- | --- |",
    ]
    for key in ("total_bets", "win_rate_pct", "total_pnl", "profit_factor", "sharpe_ratio", "max_drawdown"):
        lines.append(
            f"| {key} | {overall['selector_metrics'][key]} | {overall['all_signal_metrics'][key]} |"
        )

    lines.extend(
        [
            "",
            "## Retention",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| trade_retain_pct | {retained['trade_retain_pct']} |",
            f"| pnl_retain_pct | {retained['pnl_retain_pct']} |",
            f"| pnl_delta | {retained['pnl_delta']} |",
            f"| profit_factor_delta | {retained['profit_factor_delta']} |",
            f"| sharpe_delta | {retained['sharpe_delta']} |",
            f"| max_drawdown_delta | {retained['max_drawdown_delta']} |",
            "",
        ]
    )

    if deployment is not None:
        oos_retained = deployment["pooled_oos_comparison"]
        lines.extend(
            [
                "",
                "## Deployment Recommendation",
                "",
                f"- Recommended deploy threshold: {deployment['recommended_threshold']:.6f}",
                f"- Pooled OOS trades retained: {oos_retained['trade_retain_pct']}%",
                f"- Pooled OOS pnl retained: {oos_retained['pnl_retain_pct']}%",
                f"- Pooled OOS pnl delta: {oos_retained['pnl_delta']}",
                f"- Pooled OOS PF delta: {oos_retained['profit_factor_delta']}",
                "",
            ]
        )

    lines.extend(["", "## Split Results", ""])
    for split in results["splits"]:
        split_retained = split["comparison"]
        lines.extend(
            [
                f"### Split {split['split_index']}",
                "",
                f"- Train days: {', '.join(split['train_days'])}",
                f"- Validation days: {', '.join(split['validation_days'])}",
                f"- Embargo days: {', '.join(split['embargo_days']) if split['embargo_days'] else '(none)'}",
                f"- Test days: {', '.join(split['test_days'])}",
                f"- Chosen threshold: {split['threshold']:.6f}",
                f"- Effective threshold: {split['policy_summary']['effective_threshold']:.6f}",
                (
                    f"- Policy rows: threshold {split['policy_summary']['rows_after_threshold']} -> "
                    f"selected {split['policy_summary']['rows_after_policy']}"
                ),
                "",
                "| Block | Trades | PnL | PF | Sharpe | MaxDD |",
                "| --- | --- | --- | --- | --- | --- |",
                (
                    f"| Validation | {split['validation_metrics']['total_bets']} | "
                    f"{split['validation_metrics']['total_pnl']} | "
                    f"{split['validation_metrics']['profit_factor']} | "
                    f"{split['validation_metrics']['sharpe_ratio']} | "
                    f"{split['validation_metrics']['max_drawdown']} |"
                ),
                (
                    f"| Test Selector | {split['test_selector_metrics']['total_bets']} | "
                    f"{split['test_selector_metrics']['total_pnl']} | "
                    f"{split['test_selector_metrics']['profit_factor']} | "
                    f"{split['test_selector_metrics']['sharpe_ratio']} | "
                    f"{split['test_selector_metrics']['max_drawdown']} |"
                ),
                (
                    f"| Test All Signals | {split['test_all_signal_metrics']['total_bets']} | "
                    f"{split['test_all_signal_metrics']['total_pnl']} | "
                    f"{split['test_all_signal_metrics']['profit_factor']} | "
                    f"{split['test_all_signal_metrics']['sharpe_ratio']} | "
                    f"{split['test_all_signal_metrics']['max_drawdown']} |"
                ),
                "",
                "| Retention Metric | Value |",
                "| --- | --- |",
                f"| trade_retain_pct | {split_retained['trade_retain_pct']} |",
                f"| pnl_retain_pct | {split_retained['pnl_retain_pct']} |",
                f"| pnl_delta | {split_retained['pnl_delta']} |",
                f"| profit_factor_delta | {split_retained['profit_factor_delta']} |",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _train_one_split(
    split,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    max_depth: int,
    min_samples_leaf: int,
    min_validation_trades: int,
    min_threshold: float,
    top_k_per_day: int | None,
    top_percent_per_day: float | None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    encoder = TabularFeatureEncoder()
    train_x = encoder.fit_transform(train_df)
    validation_x = encoder.transform(validation_df)
    test_x = encoder.transform(test_df)

    model = ExpectedPnlTreeRegressor(
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )
    model.fit(train_x, train_df["realized_pnl"].to_numpy(dtype=float, copy=False))

    validation_predictions = model.predict(validation_x)
    threshold, validation_metrics, _ = choose_prediction_threshold(
        validation_df,
        validation_predictions,
        min_trades=min_validation_trades,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )

    test_predictions = model.predict(test_x)
    test_positive_rate = model.predict_positive_rate(test_x)
    all_predictions = test_df.copy()
    all_predictions["predicted_pnl"] = test_predictions
    all_predictions["predicted_positive_rate"] = test_positive_rate
    selected, policy_summary = apply_selection_policy(
        all_predictions,
        threshold=threshold,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )
    all_predictions["selected_by_meta_model"] = all_predictions.index.isin(selected.index)
    selected = selected.copy()
    selected["selected_by_meta_model"] = True

    selector_metrics = compute_signal_metrics(
        selected,
        config_id=f"selector_split_{split.split_index}",
    )
    baseline_metrics = compute_signal_metrics(
        test_df,
        config_id=f"all_signals_split_{split.split_index}",
    )

    split_result = {
        **split.to_dict(),
        "threshold": float(threshold),
        "policy_summary": policy_summary,
        "train_rows": int(len(train_df)),
        "validation_rows": int(len(validation_df)),
        "test_rows": int(len(test_df)),
        "validation_metrics": validation_metrics,
        "test_selector_metrics": selector_metrics,
        "test_all_signal_metrics": baseline_metrics,
        "comparison": _policy_comparison(selector_metrics, baseline_metrics),
    }
    model_payload = model.to_dict(feature_names=encoder.feature_names_)
    return split_result, all_predictions, model_payload


def run_meta_model_pipeline(
    dataset: pd.DataFrame,
    *,
    train_days: int,
    validation_days: int,
    embargo_days: int,
    test_days: int,
    step_days: int,
    max_depth: int,
    min_samples_leaf: int,
    min_validation_trades: int,
    min_threshold: float,
    top_k_per_day: int | None,
    top_percent_per_day: float | None,
) -> dict[str, Any]:
    if dataset.empty:
        raise ValueError("dataset must not be empty")

    splits = build_embargoed_walkforward_splits(
        dataset,
        train_days=train_days,
        validation_days=validation_days,
        embargo_days=embargo_days,
        test_days=test_days,
        step_days=step_days,
    )

    split_results: list[dict[str, Any]] = []
    all_prediction_rows: list[pd.DataFrame] = []
    model_trees: dict[str, Any] = {}

    for split in splits:
        train_df, validation_df, test_df = apply_walkforward_split(dataset, split)
        if train_df.empty or validation_df.empty or test_df.empty:
            continue

        result, predictions, model_payload = _train_one_split(
            split,
            train_df,
            validation_df,
            test_df,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            min_validation_trades=min_validation_trades,
            min_threshold=min_threshold,
            top_k_per_day=top_k_per_day,
            top_percent_per_day=top_percent_per_day,
        )
        split_results.append(result)
        all_prediction_rows.append(predictions)
        model_trees[f"split_{split.split_index:02d}"] = model_payload

    if not split_results:
        raise ValueError("No non-empty walk-forward splits were produced.")

    prediction_frame = pd.concat(all_prediction_rows, ignore_index=True)
    selected_predictions = prediction_frame[prediction_frame["selected_by_meta_model"]].copy()
    selector_metrics = compute_signal_metrics(
        selected_predictions,
        config_id="selector_overall",
    )
    baseline_metrics = compute_signal_metrics(
        prediction_frame,
        config_id="all_signals_overall",
    )
    deployment = _build_deployment_artifact(
        dataset,
        prediction_frame,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        min_validation_trades=min_validation_trades,
        min_threshold=min_threshold,
        top_k_per_day=top_k_per_day,
        top_percent_per_day=top_percent_per_day,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": build_dataset_summary(dataset),
        "splits": split_results,
        "predictions": prediction_frame,
        "model_trees": model_trees,
        "policy": {
            "min_threshold": float(min_threshold),
            "top_k_per_day": top_k_per_day,
            "top_percent_per_day": top_percent_per_day,
        },
        "deployment": deployment,
        "overall": {
            "selector_metrics": selector_metrics,
            "all_signal_metrics": baseline_metrics,
            "comparison": _policy_comparison(selector_metrics, baseline_metrics),
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="analysis.train_meta_model",
        description="Train a tree-based selector on expert-signal opportunities.",
    )
    parser.add_argument(
        "--dataset-csv",
        default=None,
        help="Use an existing opportunity CSV instead of rebuilding from markets.",
    )
    parser.add_argument(
        "--experts",
        default=",".join(DEFAULT_EXPERTS),
        help="Comma-separated expert strategy IDs (default: S5,S13,S14,S15).",
    )
    parser.add_argument(
        "--config-source",
        choices=("candidate", "default", "baseline"),
        default=DEFAULT_CONFIG_SOURCE,
        help="Config source for expert strategies (default: candidate).",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Optional comma-separated asset filter.",
    )
    parser.add_argument(
        "--durations",
        default=",".join(str(value) for value in DEFAULT_DURATIONS),
        help="Comma-separated duration filter in minutes (default: 5).",
    )
    parser.add_argument("--slippage", type=float, default=0.01, help="Labeling slippage.")
    parser.add_argument("--train-days", type=int, default=3)
    parser.add_argument("--validation-days", type=int, default=1)
    parser.add_argument("--embargo-days", type=int, default=1)
    parser.add_argument("--test-days", type=int, default=1)
    parser.add_argument("--step-days", type=int, default=1)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--min-samples-leaf", type=int, default=25)
    parser.add_argument("--min-validation-trades", type=int, default=25)
    parser.add_argument(
        "--min-threshold",
        type=float,
        default=0.0,
        help="Minimum allowed predicted-PnL threshold (default: 0.0).",
    )
    parser.add_argument(
        "--top-k-per-day",
        type=int,
        default=None,
        help="Optional cap on selected signals per market day after thresholding.",
    )
    parser.add_argument(
        "--top-percent-per-day",
        type=float,
        default=None,
        help="Optional cap on selected signals per market day as a fraction in (0,1].",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to ./results/meta_model/run_<timestamp>.",
    )
    args = parser.parse_args(argv)

    if args.dataset_csv:
        print(f"Loading opportunity dataset from {args.dataset_csv}...")
        dataset = pd.read_csv(args.dataset_csv, parse_dates=["started_at"])
        resolved_experts = _experts_from_dataset(dataset)
    else:
        print("Loading markets...")
        markets = data_loader.load_all_data()
        if not markets:
            raise SystemExit("No markets loaded.")

        assets = _parse_csv_list(args.assets)
        durations = _parse_duration_list(args.durations)
        markets = data_loader.filter_markets(markets, assets=assets, durations=durations)
        if not markets:
            raise SystemExit("No markets remain after applying filters.")

        expert_ids = _parse_csv_list(args.experts) or list(DEFAULT_EXPERTS)
        resolved_experts = expert_ids
        print(f"Building opportunity dataset from experts: {expert_ids}")
        dataset = build_opportunity_dataset(
            markets,
            expert_ids=expert_ids,
            config_source=args.config_source,
            slippage=args.slippage,
        )

    results = run_meta_model_pipeline(
        dataset,
        train_days=args.train_days,
        validation_days=args.validation_days,
        embargo_days=args.embargo_days,
        test_days=args.test_days,
        step_days=args.step_days,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_samples_leaf,
        min_validation_trades=args.min_validation_trades,
        min_threshold=args.min_threshold,
        top_k_per_day=args.top_k_per_day,
        top_percent_per_day=args.top_percent_per_day,
    )

    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    opportunities_path = output_dir / "opportunities.csv"
    predictions_path = output_dir / "predictions.csv"
    json_path = output_dir / "summary.json"
    markdown_path = output_dir / "summary.md"
    trees_path = output_dir / "trees.json"
    deploy_bundle_path = output_dir / "deploy_bundle.json"

    dataset.to_csv(opportunities_path, index=False)
    results["predictions"].to_csv(predictions_path, index=False)

    payload = {
        key: value
        for key, value in results.items()
        if key not in {"predictions", "model_trees"}
    }
    payload["experts"] = resolved_experts or (_parse_csv_list(args.experts) or list(DEFAULT_EXPERTS))
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    with trees_path.open("w", encoding="utf-8") as handle:
        json.dump(results["model_trees"], handle, indent=2)
        handle.write("\n")

    deploy_bundle = {
        "bundle_version": 1,
        "generated_at": results["generated_at"],
        "experts": payload["experts"],
        "dataset": results["dataset"],
        "deployment": results["deployment"],
    }
    with deploy_bundle_path.open("w", encoding="utf-8") as handle:
        json.dump(deploy_bundle, handle, indent=2)
        handle.write("\n")

    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write(_render_markdown(payload))

    selector_metrics = results["overall"]["selector_metrics"]
    baseline_metrics = results["overall"]["all_signal_metrics"]
    print("\n=== Meta-Model Summary ===")
    print(f"Rows: {results['dataset']['rows']}")
    print(f"Splits: {len(results['splits'])}")
    print(
        f"Selector: bets={selector_metrics['total_bets']} "
        f"pnl={selector_metrics['total_pnl']:.4f} "
        f"pf={selector_metrics['profit_factor']:.4f}"
    )
    print(
        f"All signals: bets={baseline_metrics['total_bets']} "
        f"pnl={baseline_metrics['total_pnl']:.4f} "
        f"pf={baseline_metrics['profit_factor']:.4f}"
    )
    print(
        f"Retention: trades={results['overall']['comparison']['trade_retain_pct']:.2f}% "
        f"pnl={results['overall']['comparison']['pnl_retain_pct']:.2f}%"
    )
    print(
        f"Deploy threshold: {results['deployment']['recommended_threshold']:.6f} "
        f"(pooled OOS trades={results['deployment']['pooled_oos_comparison']['trade_retain_pct']:.2f}% "
        f"pnl={results['deployment']['pooled_oos_comparison']['pnl_retain_pct']:.2f}%)"
    )
    print(f"Saved opportunities: {opportunities_path.resolve()}")
    print(f"Saved predictions: {predictions_path.resolve()}")
    print(f"Saved summary: {json_path.resolve()}")
    print(f"Saved markdown: {markdown_path.resolve()}")
    print(f"Saved trees: {trees_path.resolve()}")
    print(f"Saved deploy bundle: {deploy_bundle_path.resolve()}")


if __name__ == "__main__":
    main()
