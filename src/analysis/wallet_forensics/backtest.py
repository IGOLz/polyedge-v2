"""Sequence-level backtesting for extracted wallet-forensics blueprints."""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.utils import ensure_dir, row_hash, safe_float

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest extracted wallet-forensics strategies")
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--profile", type=str, help="Polymarket profile name, for example ColdMath")
    identity_group.add_argument("--wallet", type=str, help="Proxy wallet address to analyze")
    parser.add_argument(
        "--strategy",
        type=str,
        default="inventory_rebalancing_merge",
        help="Strategy blueprint key to backtest",
    )
    parser.add_argument("--weather-only", action="store_true", help="Filter sequences to weather markets only")
    parser.add_argument("--output-dir", type=str, default=None, help="Artifact output directory")
    parser.add_argument(
        "--fill-context-path",
        type=str,
        default=None,
        help="Optional explicit path to wallet_fill_context.csv or wallet_fill_context.parquet",
    )
    parser.add_argument(
        "--require-fill-context",
        action="store_true",
        help="Fail if row-level fill-context artifacts are unavailable",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_blueprint_backtest(args)
    logger.info(
        "Blueprint backtest complete for %s with best config %s",
        result["target"]["proxy_wallet"],
        result["best_config"]["config_id"],
    )
    return 0


def run_blueprint_backtest(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    client = WalletForensicsClient()
    conn = get_connection()
    try:
        target = _resolve_target(client, args)
        output_dir = _resolve_output_dir(args, target)
        sequences = _load_playbook_sequences(
            conn,
            proxy_wallet=target["proxy_wallet"],
            strategy_key=args.strategy,
            weather_only=bool(args.weather_only),
        )
        if not sequences:
            raise RuntimeError(f"No sequences found for {args.strategy!r} and wallet {target['proxy_wallet']}")

        blueprint = _load_strategy_blueprint(
            conn,
            proxy_wallet=target["proxy_wallet"],
            strategy_key=args.strategy,
        )
        fill_context_path = _resolve_fill_context_path(args, output_dir=output_dir)
        fill_context_rows = _load_fill_context_rows(fill_context_path) if fill_context_path else []
        if args.require_fill_context and not fill_context_rows:
            raise RuntimeError(
                "Fill-context-aware backtest requested, but no row-level wallet_fill_context artifact was found"
            )

        ledger_rows = _load_sequence_ledger_rows(
            conn,
            proxy_wallet=target["proxy_wallet"],
            sequences=sequences,
        )
        enriched_sequences = enrich_inventory_merge_sequences(
            sequences=sequences,
            fill_context_rows=fill_context_rows,
            ledger_rows=ledger_rows,
        )
        fill_context_enabled = any(
            (row.get("fill_context_summary_json") or {}).get("buy_fill_context_count", 0) > 0
            for row in enriched_sequences
        )

        grid = build_inventory_merge_grid(
            blueprint=blueprint,
            sequences=enriched_sequences,
            fill_context_enabled=fill_context_enabled,
        )
        results = evaluate_inventory_merge_grid(
            sequences=enriched_sequences,
            config_rows=grid,
        )
        if results.empty:
            raise RuntimeError("Backtest grid produced no results")
        ranked = rank_inventory_merge_results(results)
        best_config = select_best_inventory_merge_config(ranked)
        paper_sequences = select_inventory_merge_sequences(enriched_sequences, best_config)
        attribution_summary = build_inventory_merge_attribution_summary(paper_sequences)
        bot_config = build_inventory_merge_bot_config(
            target=target,
            best_config=best_config,
            selected_sequences=paper_sequences,
            source_blueprint=blueprint,
            fill_context_enabled=fill_context_enabled,
            fill_context_path=str(fill_context_path) if fill_context_path else None,
            attribution_summary=attribution_summary,
        )
        export_inventory_merge_backtest_artifacts(
            output_dir=output_dir,
            target=target,
            strategy_key=args.strategy,
            ranked_results=ranked,
            best_config=best_config,
            selected_sequences=paper_sequences,
            bot_config=bot_config,
            fill_context_enabled=fill_context_enabled,
            fill_context_path=str(fill_context_path) if fill_context_path else None,
            attribution_summary=attribution_summary,
        )
        return {
            "target": target,
            "output_dir": str(output_dir),
            "strategy_key": args.strategy,
            "sequence_count": len(sequences),
            "config_count": len(ranked),
            "fill_context_applied": fill_context_enabled,
            "fill_context_path": str(fill_context_path) if fill_context_path else None,
            "best_config": best_config,
            "attribution_summary": attribution_summary,
        }
    finally:
        client.close()
        conn.close()


def build_inventory_merge_grid(
    *,
    blueprint: dict[str, Any] | None,
    sequences: list[dict[str, Any]],
    fill_context_enabled: bool = False,
) -> list[dict[str, Any]]:
    blueprint_entry = (blueprint or {}).get("entry_rule_json") or {}
    matched_sizes = [safe_float((row.get("payload_json") or {}).get("matched_size")) for row in sequences]
    matched_sizes = [value for value in matched_sizes if value is not None and value > 0.0]

    cost_candidates = _unique_sorted(
        [
            0.97,
            0.98,
            0.985,
            0.99,
            0.995,
            safe_float(blueprint_entry.get("complete_set_cost_lte")),
        ]
    )
    imbalance_candidates = _unique_sorted(
        [
            0.15,
            0.25,
            0.35,
            0.50,
            safe_float(blueprint_entry.get("max_inventory_imbalance_ratio")),
        ]
    )
    size_candidates = _unique_sorted(
        [
            0.0,
            1.0,
            5.0,
            _percentile(matched_sizes, 0.25),
            _percentile(matched_sizes, 0.50),
            _percentile(matched_sizes, 0.75),
        ]
    )
    delay_candidates = [1.0, 5.0, 15.0, 60.0, 240.0, None]

    fill_context_candidates = (
        [
            {
                "require_full_fill_context": True,
                "min_under_par_buy_fill_ratio": min_under_par_buy_fill_ratio,
                "max_worse_buy_fill_ratio": max_worse_buy_fill_ratio,
                "worse_buy_override_complete_set_cost_lte": override_complete_set_cost_lte,
            }
            for min_under_par_buy_fill_ratio in (0.50, 0.75, 1.00)
            for max_worse_buy_fill_ratio in (0.00, 0.10, 0.25)
            for override_complete_set_cost_lte in (None, 0.97, 0.98)
        ]
        if fill_context_enabled else [{}]
    )

    configs: list[dict[str, Any]] = []
    for complete_set_cost_lte in cost_candidates:
        for max_imbalance_ratio in imbalance_candidates:
            for min_matched_size in size_candidates:
                for max_merge_delay_minutes in delay_candidates:
                    for fill_context_rules in fill_context_candidates:
                        config = {
                            "strategy_key": "inventory_rebalancing_merge",
                            "complete_set_cost_lte": complete_set_cost_lte,
                            "max_inventory_imbalance_ratio": max_imbalance_ratio,
                            "min_matched_size": min_matched_size,
                            "max_merge_delay_minutes": max_merge_delay_minutes,
                            **fill_context_rules,
                        }
                        config["config_id"] = row_hash(config)
                        configs.append(config)
    return configs


def evaluate_inventory_merge_grid(
    *,
    sequences: list[dict[str, Any]],
    config_rows: Iterable[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for config in config_rows:
        selected = select_inventory_merge_sequences(sequences, config)
        metrics = _compute_sequence_metrics(selected)
        rows.append({**config, **metrics})
    return pd.DataFrame(rows)


def rank_inventory_merge_results(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    ranked = frame.copy()
    eligible_support = max(20, int(len(frame) * 0.02))
    ranked["eligible"] = ranked["support_count"] >= eligible_support

    for column in (
        "total_realized_pnl",
        "roi_pct",
        "win_rate_pct",
        "profit_factor",
        "support_count",
        "estimated_under_par_entry_edge_pnl",
        "merge_redeem_realized_pnl",
    ):
        if column in ranked:
            ranked[f"{column}_pctile"] = _pctile_series(ranked[column])
    ranked["max_drawdown_pctile"] = _pctile_series(-ranked["max_drawdown"])

    ranked["ranking_score"] = (
        ranked["eligible"].astype(float) * 25.0
        + ranked["total_realized_pnl_pctile"] * 0.28
        + ranked["roi_pct_pctile"] * 0.18
        + ranked["support_count_pctile"] * 0.18
        + ranked["win_rate_pct_pctile"] * 0.08
        + ranked["profit_factor_pctile"] * 0.08
        + ranked.get("estimated_under_par_entry_edge_pnl_pctile", 50.0) * 0.05
        + ranked.get("merge_redeem_realized_pnl_pctile", 50.0) * 0.05
        + ranked["max_drawdown_pctile"] * 0.10
    ).round(4)
    ranked = ranked.sort_values(
        ["ranking_score", "total_realized_pnl", "roi_pct", "support_count"],
        ascending=False,
        kind="mergesort",
    ).reset_index(drop=True)
    return ranked


def select_best_inventory_merge_config(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise RuntimeError("No backtest configs available")
    eligible = frame[frame["eligible"] == True]  # noqa: E712
    if not eligible.empty:
        chosen = eligible.iloc[0]
    else:
        max_support = int(frame["support_count"].max() or 0)
        support_floor = max(3, int(max_support * 0.85 + 0.999999))
        robust = frame[frame["support_count"] >= support_floor]
        chosen = robust.iloc[0] if not robust.empty else frame.iloc[0]
    return _jsonable_row(dict(chosen))


def select_inventory_merge_sequences(
    sequences: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in sequences:
        payload = row.get("payload_json") or {}
        complete_set_cost = _sequence_complete_set_cost(row)
        imbalance = safe_float(payload.get("inventory_imbalance_ratio"))
        matched_size = safe_float(payload.get("matched_size")) or 0.0
        merge_delay = safe_float(payload.get("merge_delay_minutes"))

        if complete_set_cost is None or complete_set_cost > float(config["complete_set_cost_lte"]):
            continue
        if imbalance is not None and imbalance > float(config["max_inventory_imbalance_ratio"]):
            continue
        if matched_size < float(config["min_matched_size"]):
            continue
        delay_limit = config.get("max_merge_delay_minutes")
        if delay_limit is not None and merge_delay is not None and merge_delay > float(delay_limit):
            continue
        if not _passes_fill_context_filters(row=row, config=config, complete_set_cost=complete_set_cost):
            continue
        selected.append(row)
    return selected


def build_inventory_merge_bot_config(
    *,
    target: dict[str, Any],
    best_config: dict[str, Any],
    selected_sequences: list[dict[str, Any]],
    source_blueprint: dict[str, Any] | None,
    fill_context_enabled: bool | None = None,
    fill_context_path: str | None = None,
    attribution_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payloads = [row.get("payload_json") or {} for row in selected_sequences]
    matched_sizes = [safe_float(item.get("matched_size")) for item in payloads]
    matched_sizes = [value for value in matched_sizes if value is not None]
    buy_usdc_values = [safe_float(item.get("buy_usdc")) for item in payloads]
    buy_usdc_values = [value for value in buy_usdc_values if value is not None]
    fill_context_enabled = bool(
        fill_context_enabled
        if fill_context_enabled is not None
        else best_config.get("require_full_fill_context")
    )
    attribution_summary = attribution_summary or build_inventory_merge_attribution_summary(selected_sequences)

    strategy_name = (
        "coldmath_inventory_rebalancing_merge_v2"
        if fill_context_enabled else
        "coldmath_inventory_rebalancing_merge_v1"
    )
    entry_rule: dict[str, Any] = {
        "condition": "same_condition_both_sides",
        "complete_set_cost_lte": best_config["complete_set_cost_lte"],
        "max_inventory_imbalance_ratio": best_config["max_inventory_imbalance_ratio"],
        "min_matched_size": best_config["min_matched_size"],
    }
    if fill_context_enabled:
        entry_rule.update(
            {
                "require_full_buy_fill_context": True,
                "min_under_par_buy_fill_ratio": best_config.get("min_under_par_buy_fill_ratio"),
                "preferred_price_history_execution_labels": [
                    "better_than_nearby_trade",
                    "nearby_trade_aligned",
                ],
                "max_worse_buy_fill_ratio": best_config.get("max_worse_buy_fill_ratio"),
                "worse_buy_override_complete_set_cost_lte": best_config.get(
                    "worse_buy_override_complete_set_cost_lte"
                ),
            }
        )

    result = {
        "profile_name": target.get("profile_name"),
        "proxy_wallet": target["proxy_wallet"],
        "strategy_name": strategy_name,
        "strategy_key": "inventory_rebalancing_merge",
        "execution_mode": "paper_only",
        "source_blueprint_id": (source_blueprint or {}).get("blueprint_id"),
        "entry_rule": entry_rule,
        "sizing_rule": {
            "inventory_style": "match_smaller_side_and_rebalance",
            "matched_size_target": round(_median(matched_sizes) or 0.0, 6),
            "max_sequence_buy_usdc": round(_percentile(buy_usdc_values, 0.75) or 0.0, 6),
        },
        "inventory_balancing_rule": {
            "style": "match_smaller_side_and_rebalance",
            "max_inventory_imbalance_ratio": best_config["max_inventory_imbalance_ratio"],
            "rebalance_tolerance_notional_usdc": round(_percentile(buy_usdc_values, 0.25) or 0.0, 6),
            "prefer_opposite_leg_when_pair_remains_sub_par": True,
        },
        "exit_rule": {
            "action": "merge_or_redeem_when_inventory_matched",
            "preferred_action": "merge_before_resolution",
            "fallback_action": "redeem_if_resolved",
            "max_merge_delay_minutes": best_config.get("max_merge_delay_minutes"),
            "force_flatten_before_resolution": True,
        },
        "risk_rule": {
            "avoid_unmatched_inventory": True,
            "max_complete_set_cost": best_config["complete_set_cost_lte"],
            "max_sequence_buy_usdc": round(_percentile(buy_usdc_values, 0.90) or 0.0, 6),
            "reject_missing_fill_context": fill_context_enabled,
            "tail_dust_behavior_enabled": False,
        },
        "backtest_summary": {
            "support_count": best_config["support_count"],
            "total_realized_pnl": best_config["total_realized_pnl"],
            "roi_pct": best_config["roi_pct"],
            "win_rate_pct": best_config["win_rate_pct"],
            "ranking_score": best_config["ranking_score"],
            "deployment_readiness": "paper_only" if float(best_config["support_count"]) < 20 else "candidate_for_live_scanner",
        },
        "pnl_attribution": attribution_summary,
        "fill_context_artifact_path": fill_context_path,
        "limitations": [
            "Backtest uses reconstructed public wallet sequences, not full market-wide quote history.",
            "Fill-context labels still rely mostly on nearby trade prints unless direct quote snapshots are available.",
            "Live deployment still requires a market scanner that can detect both-side sub-par complete sets in real time.",
        ],
    }
    return result


def export_inventory_merge_backtest_artifacts(
    *,
    output_dir: Path,
    target: dict[str, Any],
    strategy_key: str,
    ranked_results: pd.DataFrame,
    best_config: dict[str, Any],
    selected_sequences: list[dict[str, Any]],
    bot_config: dict[str, Any],
    fill_context_enabled: bool,
    fill_context_path: str | None,
    attribution_summary: dict[str, Any],
) -> None:
    ensure_dir(output_dir)
    base_name = f"wallet_{strategy_key}_backtest"
    ranked_results.to_csv(output_dir / f"{base_name}_results.csv", index=False)
    pd.DataFrame([best_config]).to_csv(output_dir / f"{base_name}_best_config.csv", index=False)
    pd.DataFrame(_flatten_selected_sequences(selected_sequences)).to_csv(
        output_dir / f"{base_name}_paper_sequences.csv",
        index=False,
    )
    (output_dir / f"{base_name}_bot_config.json").write_text(
        json.dumps(bot_config, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / f"{base_name}_report.md").write_text(
        build_inventory_merge_backtest_markdown(
            target=target,
            strategy_key=strategy_key,
            best_config=best_config,
            ranked_results=ranked_results,
            selected_sequences=selected_sequences,
            fill_context_enabled=fill_context_enabled,
            fill_context_path=fill_context_path,
            attribution_summary=attribution_summary,
        ),
        encoding="utf-8",
    )


def build_inventory_merge_backtest_markdown(
    *,
    target: dict[str, Any],
    strategy_key: str,
    best_config: dict[str, Any],
    ranked_results: pd.DataFrame,
    selected_sequences: list[dict[str, Any]],
    fill_context_enabled: bool,
    fill_context_path: str | None,
    attribution_summary: dict[str, Any],
) -> str:
    lines = [
        f"# Sequence Backtest: {strategy_key}",
        "",
        "## Overview",
        f"- Profile: `{target.get('profile_name') or target['proxy_wallet']}`",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Configs tested: `{len(ranked_results)}`",
        f"- Selected sequences under best config: `{best_config['support_count']}`",
        f"- Fill-context-aware mode: `{fill_context_enabled}`",
    ]
    if fill_context_path:
        lines.append(f"- Fill-context artifact: `{fill_context_path}`")

    lines.extend(
        [
            "",
            "## Best Config",
            f"- Complete set cost <= `{best_config['complete_set_cost_lte']}`",
            f"- Inventory imbalance <= `{best_config['max_inventory_imbalance_ratio']}`",
            f"- Min matched size >= `{best_config['min_matched_size']}`",
            f"- Max merge delay minutes: `{best_config['max_merge_delay_minutes']}`",
        ]
    )
    if fill_context_enabled:
        lines.extend(
            [
                f"- Require full buy-fill context: `{best_config.get('require_full_fill_context')}`",
                f"- Under-par buy-fill ratio >= `{best_config.get('min_under_par_buy_fill_ratio')}`",
                f"- Max worse-than-nearby-buy ratio <= `{best_config.get('max_worse_buy_fill_ratio')}`",
                f"- Worse-fill override complete-set cost <= `{best_config.get('worse_buy_override_complete_set_cost_lte')}`",
            ]
        )
    lines.extend(
        [
            f"- Total realized PnL: `{best_config['total_realized_pnl']:.2f}`",
            f"- ROI: `{best_config['roi_pct']:.2f}%`",
            f"- Win rate: `{best_config['win_rate_pct']:.2f}%`",
            f"- Profit factor: `{best_config['profit_factor']:.2f}`",
            f"- Max drawdown: `{best_config['max_drawdown']:.2f}`",
            "",
            "## PnL Attribution",
            f"- Estimated under-par entry edge: `{attribution_summary.get('estimated_under_par_entry_edge_pnl', 0.0):.2f}`",
            f"- Realized via merge/redeem: `{attribution_summary.get('merge_redeem_realized_pnl', 0.0):.2f}`",
            f"- Realized via sell-side inventory rebalancing: `{attribution_summary.get('inventory_rebalancing_realized_pnl', 0.0):.2f}`",
            f"- Tail/dust residual realized PnL: `{attribution_summary.get('tail_dust_residual_realized_pnl', 0.0):.2f}`",
            f"- Other residual realized PnL: `{attribution_summary.get('other_residual_realized_pnl', 0.0):.2f}`",
        ]
    )
    if fill_context_enabled:
        lines.extend(
            [
                f"- Avg under-par buy-fill ratio: `{attribution_summary.get('avg_under_par_buy_fill_ratio')}`",
                f"- Avg worse-than-nearby-buy ratio: `{attribution_summary.get('avg_worse_buy_fill_ratio')}`",
                f"- Sequences with full buy-fill context: `{attribution_summary.get('full_fill_context_sequence_count', 0)}`",
            ]
        )

    lines.extend(["", "## Top Configs"])
    for row in ranked_results.head(10).to_dict(orient="records"):
        segments = [
            f"score `{row['ranking_score']:.2f}`",
            f"pnl `{row['total_realized_pnl']:.2f}`",
            f"roi `{row['roi_pct']:.2f}%`",
            f"support `{int(row['support_count'])}`",
            f"cost<=`{row['complete_set_cost_lte']}`",
            f"imbalance<=`{row['max_inventory_imbalance_ratio']}`",
            f"matched>=`{row['min_matched_size']}`",
            f"delay<=`{row['max_merge_delay_minutes']}`",
        ]
        if fill_context_enabled:
            segments.extend(
                [
                    f"under_par>=`{row.get('min_under_par_buy_fill_ratio')}`",
                    f"worse<=`{row.get('max_worse_buy_fill_ratio')}`",
                    f"override<=`{row.get('worse_buy_override_complete_set_cost_lte')}`",
                ]
            )
        lines.append("- " + " | ".join(segments))

    lines.extend(["", "## Sample Sequences"])
    if not selected_sequences:
        lines.append("- No sequences matched the best config.")
    else:
        for row in selected_sequences[:10]:
            payload = row.get("payload_json") or {}
            fill_context_summary = row.get("fill_context_summary_json") or {}
            pnl_attribution = row.get("pnl_attribution_json") or {}
            sample_segments = [
                f"`{row.get('condition_id')}` pnl `{float(row.get('realized_pnl') or 0.0):.2f}`",
                f"cost `{_sequence_complete_set_cost(row)}`",
                f"matched `{payload.get('matched_size')}`",
                f"delay `{payload.get('merge_delay_minutes')}`",
            ]
            if fill_context_enabled:
                sample_segments.extend(
                    [
                        f"under_par_ratio `{fill_context_summary.get('under_par_buy_fill_ratio')}`",
                        f"worse_ratio `{fill_context_summary.get('worse_buy_fill_ratio')}`",
                    ]
                )
            sample_segments.append(
                f"merge/redeem `{pnl_attribution.get('merge_redeem_realized_pnl')}`"
            )
            lines.append("- " + ", ".join(sample_segments))
    return "\n".join(lines) + "\n"


def _resolve_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.profile:
        resolved = client.resolve_wallet(args.profile)
        wallet = _extract_wallet(resolved)
        if not wallet:
            raise RuntimeError(f"Could not resolve proxy wallet for profile {args.profile!r}")
        profile_name = resolved.get("name") or args.profile
    else:
        wallet = str(args.wallet or "").strip().lower()
        if not wallet:
            raise RuntimeError("Wallet address is required")
        profile_name = None
    return {
        "proxy_wallet": wallet,
        "profile_name": profile_name,
    }


def _extract_wallet(payload: dict[str, Any]) -> str | None:
    for key in ("proxyWallet", "proxy_wallet", "walletAddress", "wallet", "address"):
        value = payload.get(key)
        if value:
            return str(value).strip().lower()
    return None


def _resolve_output_dir(args: argparse.Namespace, target: dict[str, Any]) -> Path:
    if args.output_dir:
        return ensure_dir(Path(args.output_dir).resolve())
    label = str(target.get("profile_name") or target["proxy_wallet"]).lower().replace("/", "-")
    return ensure_dir(Path(__file__).resolve().parents[2] / "results" / "wallet_forensics" / label)


def _resolve_fill_context_path(args: argparse.Namespace, *, output_dir: Path) -> Path | None:
    if args.fill_context_path:
        candidate = Path(args.fill_context_path).expanduser().resolve()
        if not candidate.exists():
            raise RuntimeError(f"Fill-context artifact not found at {candidate}")
        return candidate
    for name in ("wallet_fill_context.parquet", "wallet_fill_context.csv"):
        candidate = output_dir / name
        if candidate.exists():
            return candidate
    return None


def _load_fill_context_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)
    return [_normalize_fill_context_row(row) for row in frame.to_dict(orient="records")]


def _normalize_fill_context_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: _none_if_nan(value) for key, value in row.items()}
    for key in (
        "executed_price",
        "executed_size",
        "price_history_execution_edge_bps",
        "executed_plus_opposite_price_history",
    ):
        result[key] = safe_float(result.get(key))
    for key in ("token_mapping_found", "is_weather", "local_pair_under_par", "price_history_pair_under_par"):
        result[key] = _parse_optional_bool(result.get(key))
    if result.get("ledger_event_id") is not None:
        result["ledger_event_id"] = str(result["ledger_event_id"])
    if result.get("condition_id") is not None:
        result["condition_id"] = str(result["condition_id"])
    return result


def _load_playbook_sequences(
    conn,
    *,
    proxy_wallet: str,
    strategy_key: str,
    weather_only: bool,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            sequence_id,
            proxy_wallet,
            strategy_key,
            strategy_tags_json,
            scope_type,
            scope_id,
            condition_id,
            event_slug,
            started_at,
            ended_at,
            duration_minutes,
            trade_count,
            buy_count,
            merge_count,
            redeem_count,
            distinct_conditions,
            realized_pnl,
            confidence,
            summary,
            payload_json
        FROM wallet_playbook_sequences
        WHERE proxy_wallet = %s
          AND strategy_key = %s
    """
    params: list[Any] = [proxy_wallet, strategy_key]
    if weather_only:
        sql += """
          AND condition_id IN (
              SELECT market_id
              FROM weather_market_catalog
          )
        """
    sql += " ORDER BY started_at ASC, sequence_id ASC"
    rows = load_rows(conn, sql, tuple(params))
    return [_normalize_sequence_row(row) for row in rows]


def _load_strategy_blueprint(
    conn,
    *,
    proxy_wallet: str,
    strategy_key: str,
) -> dict[str, Any] | None:
    rows = load_rows(
        conn,
        """
        SELECT
            blueprint_id,
            proxy_wallet,
            strategy_key,
            status,
            confidence,
            priority_score,
            support_count,
            distinct_conditions,
            distinct_events,
            realized_pnl_total,
            realized_pnl_avg,
            win_rate,
            summary,
            entry_rule_json,
            sizing_rule_json,
            exit_rule_json,
            risk_rule_json,
            evidence_json
        FROM wallet_strategy_blueprints
        WHERE proxy_wallet = %s
          AND strategy_key = %s
        LIMIT 1
        """,
        (proxy_wallet, strategy_key),
    )
    if not rows:
        return None
    return rows[0]


def _load_sequence_ledger_rows(
    conn,
    *,
    proxy_wallet: str,
    sequences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not sequences:
        return []
    started_at = min(row.get("started_at") for row in sequences if row.get("started_at") is not None)
    ended_at = max(row.get("ended_at") for row in sequences if row.get("ended_at") is not None)
    if started_at is None or ended_at is None:
        return []

    condition_ids = sorted(
        {
            str(row.get("condition_id") or "")
            for row in sequences
            if str(row.get("condition_id") or "")
        }
    )
    sql = """
        SELECT
            ledger_event_id,
            proxy_wallet,
            occurred_at,
            transaction_hash,
            condition_id,
            event_slug,
            asset,
            outcome,
            side,
            event_type,
            size,
            token_delta,
            usdc_delta,
            price,
            realized_pnl
        FROM wallet_ledger_events
        WHERE proxy_wallet = %s
          AND occurred_at >= %s
          AND occurred_at <= %s
    """
    params: list[Any] = [proxy_wallet, started_at, ended_at]
    if condition_ids:
        placeholders = ", ".join(["%s"] * len(condition_ids))
        sql += f" AND condition_id IN ({placeholders})"
        params.extend(condition_ids)
    sql += " ORDER BY occurred_at ASC, ledger_event_id ASC"
    return load_rows(conn, sql, tuple(params))


def enrich_inventory_merge_sequences(
    *,
    sequences: list[dict[str, Any]],
    fill_context_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fill_context_by_ledger_id = {
        str(row.get("ledger_event_id") or ""): row
        for row in fill_context_rows
        if str(row.get("ledger_event_id") or "")
    }
    ledger_rows_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        ledger_rows_by_condition[str(row.get("condition_id") or "")].append(row)

    enriched: list[dict[str, Any]] = []
    for row in sequences:
        sequence = dict(row)
        sequence["payload_json"] = dict(sequence.get("payload_json") or {})
        fill_context_summary = _build_sequence_fill_context_summary(sequence, fill_context_by_ledger_id)
        pnl_attribution = _build_sequence_pnl_attribution(
            sequence,
            ledger_rows_by_condition.get(str(sequence.get("condition_id") or ""), []),
        )
        sequence["fill_context_summary_json"] = fill_context_summary
        sequence["pnl_attribution_json"] = pnl_attribution
        enriched.append(sequence)
    return enriched


def build_inventory_merge_attribution_summary(sequences: list[dict[str, Any]]) -> dict[str, Any]:
    fill_context_ratios = [
        safe_float((row.get("fill_context_summary_json") or {}).get("under_par_buy_fill_ratio"))
        for row in sequences
    ]
    fill_context_ratios = [value for value in fill_context_ratios if value is not None]
    worse_ratios = [
        safe_float((row.get("fill_context_summary_json") or {}).get("worse_buy_fill_ratio"))
        for row in sequences
    ]
    worse_ratios = [value for value in worse_ratios if value is not None]

    return {
        "support_count": len(sequences),
        "total_realized_pnl": round(sum(safe_float(row.get("realized_pnl")) or 0.0 for row in sequences), 6),
        "estimated_under_par_entry_edge_pnl": round(
            sum(
                safe_float((row.get("pnl_attribution_json") or {}).get("estimated_under_par_entry_edge_pnl")) or 0.0
                for row in sequences
            ),
            6,
        ),
        "merge_redeem_realized_pnl": round(
            sum(
                safe_float((row.get("pnl_attribution_json") or {}).get("merge_redeem_realized_pnl")) or 0.0
                for row in sequences
            ),
            6,
        ),
        "inventory_rebalancing_realized_pnl": round(
            sum(
                safe_float((row.get("pnl_attribution_json") or {}).get("inventory_rebalancing_realized_pnl")) or 0.0
                for row in sequences
            ),
            6,
        ),
        "tail_dust_residual_realized_pnl": round(
            sum(
                safe_float((row.get("pnl_attribution_json") or {}).get("tail_dust_residual_realized_pnl")) or 0.0
                for row in sequences
            ),
            6,
        ),
        "other_residual_realized_pnl": round(
            sum(
                safe_float((row.get("pnl_attribution_json") or {}).get("other_residual_realized_pnl")) or 0.0
                for row in sequences
            ),
            6,
        ),
        "avg_under_par_buy_fill_ratio": round(mean(fill_context_ratios), 6) if fill_context_ratios else None,
        "avg_worse_buy_fill_ratio": round(mean(worse_ratios), 6) if worse_ratios else None,
        "full_fill_context_sequence_count": sum(
            1
            for row in sequences
            if bool((row.get("fill_context_summary_json") or {}).get("has_full_buy_fill_context"))
        ),
    }


def _build_sequence_fill_context_summary(
    sequence: dict[str, Any],
    fill_context_by_ledger_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = sequence.get("payload_json") or {}
    buy_trade_ids = [
        str(item).strip()
        for item in (payload.get("buy_trade_ids") or [])
        if str(item).strip()
    ]
    matched_rows = [fill_context_by_ledger_id[item] for item in buy_trade_ids if item in fill_context_by_ledger_id]
    label_counts: dict[str, int] = defaultdict(int)
    under_par_count = 0
    full_pair_count = 0
    for row in matched_rows:
        label = str(row.get("price_history_execution_label") or "")
        if label:
            label_counts[label] += 1
        if bool(row.get("price_history_pair_under_par")):
            under_par_count += 1
        if str(row.get("price_history_coverage") or "") == "full_pair":
            full_pair_count += 1

    buy_trade_count = len(buy_trade_ids)
    buy_fill_context_count = len(matched_rows)
    better_count = label_counts.get("better_than_nearby_trade", 0)
    aligned_count = label_counts.get("nearby_trade_aligned", 0)
    worse_count = label_counts.get("worse_than_nearby_trade", 0)
    dominant_label = None
    if label_counts:
        dominant_label = sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    return {
        "buy_trade_count": buy_trade_count,
        "buy_fill_context_count": buy_fill_context_count,
        "buy_fill_context_ratio": round(buy_fill_context_count / buy_trade_count, 6) if buy_trade_count else None,
        "has_full_buy_fill_context": bool(
            buy_trade_count > 0
            and buy_fill_context_count == buy_trade_count
            and full_pair_count == buy_fill_context_count
        ),
        "under_par_buy_fill_count": under_par_count,
        "under_par_buy_fill_ratio": round(under_par_count / buy_fill_context_count, 6)
        if buy_fill_context_count else None,
        "better_buy_fill_count": better_count,
        "aligned_buy_fill_count": aligned_count,
        "worse_buy_fill_count": worse_count,
        "good_buy_fill_ratio": round((better_count + aligned_count) / buy_fill_context_count, 6)
        if buy_fill_context_count else None,
        "worse_buy_fill_ratio": round(worse_count / buy_fill_context_count, 6)
        if buy_fill_context_count else None,
        "dominant_execution_label": dominant_label,
    }


def _build_sequence_pnl_attribution(
    sequence: dict[str, Any],
    condition_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    started_at = sequence.get("started_at")
    ended_at = sequence.get("ended_at")
    scoped_rows = [
        row
        for row in condition_rows
        if started_at is not None
        and ended_at is not None
        and row.get("occurred_at") is not None
        and started_at <= row["occurred_at"] <= ended_at
    ]
    merge_redeem_realized_pnl = sum(
        safe_float(row.get("realized_pnl")) or 0.0
        for row in scoped_rows
        if str(row.get("event_type") or "") in {"merge", "redeem"}
    )
    inventory_rebalancing_realized_pnl = sum(
        safe_float(row.get("realized_pnl")) or 0.0
        for row in scoped_rows
        if str(row.get("event_type") or "") == "trade" and str(row.get("side") or "") == "sell"
    )
    realized_pnl = safe_float(sequence.get("realized_pnl")) or 0.0
    residual_realized_pnl = realized_pnl - merge_redeem_realized_pnl - inventory_rebalancing_realized_pnl

    payload = sequence.get("payload_json") or {}
    min_entry_price = safe_float(payload.get("min_entry_price"))
    strategy_tags = {str(item) for item in (sequence.get("strategy_tags_json") or []) if str(item)}
    is_tail_dust = "dust_long_tail_bucket" in strategy_tags or (
        min_entry_price is not None and min_entry_price <= 0.02
    )
    tail_dust_residual_realized_pnl = residual_realized_pnl if is_tail_dust else 0.0
    other_residual_realized_pnl = residual_realized_pnl - tail_dust_residual_realized_pnl

    matched_size = safe_float(payload.get("matched_size")) or 0.0
    complete_set_cost = _sequence_complete_set_cost(sequence)
    estimated_under_par_entry_edge_pnl = 0.0
    if complete_set_cost is not None and matched_size > 0.0:
        estimated_under_par_entry_edge_pnl = max(0.0, 1.0 - complete_set_cost) * matched_size

    return {
        "estimated_under_par_entry_edge_pnl": round(estimated_under_par_entry_edge_pnl, 6),
        "merge_redeem_realized_pnl": round(merge_redeem_realized_pnl, 6),
        "inventory_rebalancing_realized_pnl": round(inventory_rebalancing_realized_pnl, 6),
        "tail_dust_residual_realized_pnl": round(tail_dust_residual_realized_pnl, 6),
        "other_residual_realized_pnl": round(other_residual_realized_pnl, 6),
        "has_tail_dust_behavior": is_tail_dust,
        "terminal_event_type": payload.get("terminal_event_type"),
    }


def _normalize_sequence_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["payload_json"] = normalized.get("payload_json") or {}
    normalized["strategy_tags_json"] = normalized.get("strategy_tags_json") or []
    return normalized


def _compute_sequence_metrics(selected: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [safe_float(row.get("realized_pnl")) or 0.0 for row in selected]
    buy_usdc = [
        safe_float((row.get("payload_json") or {}).get("buy_usdc")) or 0.0
        for row in selected
    ]
    support = len(selected)
    positive = [value for value in realized if value > 0.0]
    negative = [value for value in realized if value < 0.0]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in realized:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    total_buy_usdc = sum(buy_usdc)
    total_realized = sum(realized)
    roi_pct = (total_realized / total_buy_usdc * 100.0) if total_buy_usdc > 0 else 0.0
    profit_factor = sum(positive) / abs(sum(negative)) if negative else (999.0 if positive else 0.0)
    attribution_summary = build_inventory_merge_attribution_summary(selected)
    return {
        "support_count": support,
        "positive_sequence_count": len(positive),
        "negative_sequence_count": len(negative),
        "total_realized_pnl": total_realized,
        "avg_realized_pnl": mean(realized) if realized else 0.0,
        "median_realized_pnl": _median(realized) or 0.0,
        "win_rate_pct": (len(positive) / support * 100.0) if support else 0.0,
        "profit_factor": profit_factor,
        "total_buy_usdc": total_buy_usdc,
        "roi_pct": roi_pct,
        "max_drawdown": max_drawdown,
        "estimated_under_par_entry_edge_pnl": attribution_summary["estimated_under_par_entry_edge_pnl"],
        "merge_redeem_realized_pnl": attribution_summary["merge_redeem_realized_pnl"],
        "inventory_rebalancing_realized_pnl": attribution_summary["inventory_rebalancing_realized_pnl"],
        "tail_dust_residual_realized_pnl": attribution_summary["tail_dust_residual_realized_pnl"],
        "other_residual_realized_pnl": attribution_summary["other_residual_realized_pnl"],
        "avg_under_par_buy_fill_ratio": attribution_summary["avg_under_par_buy_fill_ratio"],
        "avg_worse_buy_fill_ratio": attribution_summary["avg_worse_buy_fill_ratio"],
    }


def _flatten_selected_sequences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload_json") or {}
        fill_context_summary = row.get("fill_context_summary_json") or {}
        pnl_attribution = row.get("pnl_attribution_json") or {}
        flattened.append(
            {
                "sequence_id": row.get("sequence_id"),
                "condition_id": row.get("condition_id"),
                "event_slug": row.get("event_slug"),
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "trade_count": row.get("trade_count"),
                "buy_count": row.get("buy_count"),
                "merge_count": row.get("merge_count"),
                "realized_pnl": row.get("realized_pnl"),
                "confidence": row.get("confidence"),
                "actionable_complete_set_cost": _sequence_complete_set_cost(row),
                "complete_set_cost": payload.get("complete_set_cost"),
                "inventory_imbalance_ratio": payload.get("inventory_imbalance_ratio"),
                "matched_size": payload.get("matched_size"),
                "merge_delay_minutes": payload.get("merge_delay_minutes"),
                "buy_usdc": payload.get("buy_usdc"),
                "buy_fill_context_ratio": fill_context_summary.get("buy_fill_context_ratio"),
                "under_par_buy_fill_ratio": fill_context_summary.get("under_par_buy_fill_ratio"),
                "good_buy_fill_ratio": fill_context_summary.get("good_buy_fill_ratio"),
                "worse_buy_fill_ratio": fill_context_summary.get("worse_buy_fill_ratio"),
                "estimated_under_par_entry_edge_pnl": pnl_attribution.get("estimated_under_par_entry_edge_pnl"),
                "merge_redeem_realized_pnl": pnl_attribution.get("merge_redeem_realized_pnl"),
                "inventory_rebalancing_realized_pnl": pnl_attribution.get("inventory_rebalancing_realized_pnl"),
                "tail_dust_residual_realized_pnl": pnl_attribution.get("tail_dust_residual_realized_pnl"),
                "other_residual_realized_pnl": pnl_attribution.get("other_residual_realized_pnl"),
            }
        )
    return flattened


def _sequence_complete_set_cost(row: dict[str, Any]) -> float | None:
    payload = row.get("payload_json") or {}
    matched_size = safe_float(payload.get("matched_size"))
    realized_pnl = safe_float(row.get("realized_pnl"))
    if matched_size is not None and matched_size > 0.0 and realized_pnl is not None:
        return 1.0 - (realized_pnl / matched_size)
    return safe_float(payload.get("complete_set_cost"))


def _passes_fill_context_filters(
    *,
    row: dict[str, Any],
    config: dict[str, Any],
    complete_set_cost: float | None,
) -> bool:
    if not any(
        key in config
        for key in (
            "require_full_fill_context",
            "min_under_par_buy_fill_ratio",
            "max_worse_buy_fill_ratio",
            "worse_buy_override_complete_set_cost_lte",
        )
    ):
        return True

    fill_context_summary = row.get("fill_context_summary_json") or {}
    buy_trade_count = int(fill_context_summary.get("buy_trade_count") or 0)
    buy_fill_context_count = int(fill_context_summary.get("buy_fill_context_count") or 0)
    if bool(config.get("require_full_fill_context")):
        if buy_trade_count <= 0 or buy_fill_context_count != buy_trade_count:
            return False
        if not bool(fill_context_summary.get("has_full_buy_fill_context")):
            return False

    min_under_par_ratio = safe_float(config.get("min_under_par_buy_fill_ratio"))
    under_par_ratio = safe_float(fill_context_summary.get("under_par_buy_fill_ratio"))
    if min_under_par_ratio is not None:
        if under_par_ratio is None or under_par_ratio < min_under_par_ratio:
            return False

    max_worse_ratio = safe_float(config.get("max_worse_buy_fill_ratio"))
    worse_ratio = safe_float(fill_context_summary.get("worse_buy_fill_ratio"))
    if max_worse_ratio is not None:
        if worse_ratio is None:
            return False
        if worse_ratio > max_worse_ratio:
            override_cost = safe_float(config.get("worse_buy_override_complete_set_cost_lte"))
            if override_cost is None or complete_set_cost is None or complete_set_cost > override_cost:
                return False

    return True


def _pctile_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float)
    if series.nunique(dropna=False) <= 1:
        return pd.Series([50.0] * len(series), index=series.index, dtype=float)
    return series.rank(pct=True) * 100.0


def _unique_sorted(values: Iterable[float | None]) -> list[float]:
    result = sorted({round(float(value), 6) for value in values if value is not None and float(value) >= 0.0})
    return result


def _median(values: Iterable[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _percentile(values: Iterable[float], ratio: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * ratio))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _none_if_nan(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return value
    is_na = pd.isna(value)
    if hasattr(is_na, "__iter__"):
        return value
    if is_na:
        return None
    return value


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "item"):
            value = value.item()
        if not isinstance(value, (dict, list, tuple, set)):
            is_na = pd.isna(value)
            if not hasattr(is_na, "__iter__") and is_na:
                value = None
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
