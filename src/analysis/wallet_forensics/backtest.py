"""Sequence-level backtesting for extracted wallet-forensics blueprints."""

from __future__ import annotations

import argparse
import json
import logging
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
        grid = build_inventory_merge_grid(blueprint=blueprint, sequences=sequences)
        results = evaluate_inventory_merge_grid(
            sequences=sequences,
            config_rows=grid,
        )
        if results.empty:
            raise RuntimeError("Backtest grid produced no results")
        ranked = rank_inventory_merge_results(results)
        best_config = select_best_inventory_merge_config(ranked)
        paper_sequences = select_inventory_merge_sequences(sequences, best_config)
        bot_config = build_inventory_merge_bot_config(
            target=target,
            best_config=best_config,
            selected_sequences=paper_sequences,
            source_blueprint=blueprint,
        )
        export_inventory_merge_backtest_artifacts(
            output_dir=output_dir,
            target=target,
            strategy_key=args.strategy,
            ranked_results=ranked,
            best_config=best_config,
            selected_sequences=paper_sequences,
            bot_config=bot_config,
        )
        return {
            "target": target,
            "output_dir": str(output_dir),
            "strategy_key": args.strategy,
            "sequence_count": len(sequences),
            "config_count": len(ranked),
            "best_config": best_config,
        }
    finally:
        client.close()
        conn.close()


def build_inventory_merge_grid(
    *,
    blueprint: dict[str, Any] | None,
    sequences: list[dict[str, Any]],
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

    configs: list[dict[str, Any]] = []
    for complete_set_cost_lte in cost_candidates:
        for max_imbalance_ratio in imbalance_candidates:
            for min_matched_size in size_candidates:
                for max_merge_delay_minutes in delay_candidates:
                    config = {
                        "strategy_key": "inventory_rebalancing_merge",
                        "complete_set_cost_lte": complete_set_cost_lte,
                        "max_inventory_imbalance_ratio": max_imbalance_ratio,
                        "min_matched_size": min_matched_size,
                        "max_merge_delay_minutes": max_merge_delay_minutes,
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

    for column in ("total_realized_pnl", "roi_pct", "win_rate_pct", "profit_factor", "support_count"):
        ranked[f"{column}_pctile"] = _pctile_series(ranked[column])
    ranked["max_drawdown_pctile"] = _pctile_series(-ranked["max_drawdown"])

    ranked["ranking_score"] = (
        ranked["eligible"].astype(float) * 25.0
        + ranked["total_realized_pnl_pctile"] * 0.30
        + ranked["roi_pct_pctile"] * 0.20
        + ranked["support_count_pctile"] * 0.20
        + ranked["win_rate_pct_pctile"] * 0.10
        + ranked["profit_factor_pctile"] * 0.10
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
        selected.append(row)
    return selected


def build_inventory_merge_bot_config(
    *,
    target: dict[str, Any],
    best_config: dict[str, Any],
    selected_sequences: list[dict[str, Any]],
    source_blueprint: dict[str, Any] | None,
) -> dict[str, Any]:
    payloads = [row.get("payload_json") or {} for row in selected_sequences]
    matched_sizes = [safe_float(item.get("matched_size")) for item in payloads]
    matched_sizes = [value for value in matched_sizes if value is not None]
    buy_usdc_values = [safe_float(item.get("buy_usdc")) for item in payloads]
    buy_usdc_values = [value for value in buy_usdc_values if value is not None]
    result = {
        "profile_name": target.get("profile_name"),
        "proxy_wallet": target["proxy_wallet"],
        "strategy_name": "coldmath_inventory_rebalancing_merge_v1",
        "strategy_key": "inventory_rebalancing_merge",
        "source_blueprint_id": (source_blueprint or {}).get("blueprint_id"),
        "entry_rule": {
            "condition": "same_condition_both_sides",
            "complete_set_cost_lte": best_config["complete_set_cost_lte"],
            "max_inventory_imbalance_ratio": best_config["max_inventory_imbalance_ratio"],
            "min_matched_size": best_config["min_matched_size"],
        },
        "sizing_rule": {
            "inventory_style": "match_smaller_side_and_rebalance",
            "matched_size_target": round(_median(matched_sizes) or 0.0, 6),
            "max_sequence_buy_usdc": round(_percentile(buy_usdc_values, 0.75) or 0.0, 6),
        },
        "exit_rule": {
            "action": "merge_when_inventory_matched",
            "max_merge_delay_minutes": best_config.get("max_merge_delay_minutes"),
            "force_flatten_before_resolution": True,
        },
        "risk_rule": {
            "avoid_unmatched_inventory": True,
            "max_complete_set_cost": best_config["complete_set_cost_lte"],
            "max_sequence_buy_usdc": round(_percentile(buy_usdc_values, 0.90) or 0.0, 6),
        },
        "backtest_summary": {
            "support_count": best_config["support_count"],
            "total_realized_pnl": best_config["total_realized_pnl"],
            "roi_pct": best_config["roi_pct"],
            "win_rate_pct": best_config["win_rate_pct"],
            "ranking_score": best_config["ranking_score"],
            "deployment_readiness": "paper_only" if float(best_config["support_count"]) < 20 else "candidate_for_live_scanner",
        },
        "limitations": [
            "Backtest uses reconstructed public wallet sequences, not full market-wide quote history.",
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
) -> str:
    lines = [
        f"# Sequence Backtest: {strategy_key}",
        "",
        "## Overview",
        f"- Profile: `{target.get('profile_name') or target['proxy_wallet']}`",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Configs tested: `{len(ranked_results)}`",
        f"- Selected sequences under best config: `{best_config['support_count']}`",
        "",
        "## Best Config",
        f"- Complete set cost <= `{best_config['complete_set_cost_lte']}`",
        f"- Inventory imbalance <= `{best_config['max_inventory_imbalance_ratio']}`",
        f"- Min matched size >= `{best_config['min_matched_size']}`",
        f"- Max merge delay minutes: `{best_config['max_merge_delay_minutes']}`",
        f"- Total realized PnL: `{best_config['total_realized_pnl']:.2f}`",
        f"- ROI: `{best_config['roi_pct']:.2f}%`",
        f"- Win rate: `{best_config['win_rate_pct']:.2f}%`",
        f"- Profit factor: `{best_config['profit_factor']:.2f}`",
        f"- Max drawdown: `{best_config['max_drawdown']:.2f}`",
        "",
        "## Top Configs",
    ]
    for row in ranked_results.head(10).to_dict(orient="records"):
        lines.append(
            "- "
            f"score `{row['ranking_score']:.2f}` | pnl `{row['total_realized_pnl']:.2f}` | "
            f"roi `{row['roi_pct']:.2f}%` | support `{int(row['support_count'])}` | "
            f"cost<=`{row['complete_set_cost_lte']}` | imbalance<=`{row['max_inventory_imbalance_ratio']}` | "
            f"matched>=`{row['min_matched_size']}` | delay<=`{row['max_merge_delay_minutes']}`"
        )

    lines.extend(["", "## Sample Sequences"])
    if not selected_sequences:
        lines.append("- No sequences matched the best config.")
    else:
        for row in selected_sequences[:10]:
            payload = row.get("payload_json") or {}
            lines.append(
                "- "
                f"`{row.get('condition_id')}` pnl `{float(row.get('realized_pnl') or 0.0):.2f}`, "
                f"cost `{_sequence_complete_set_cost(row)}`, "
                f"matched `{payload.get('matched_size')}`, "
                f"delay `{payload.get('merge_delay_minutes')}`"
            )
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
    }


def _flatten_selected_sequences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload_json") or {}
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


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "item"):
            value = value.item()
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
