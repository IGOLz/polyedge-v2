"""Paper scanner for live weather merge candidates derived from wallet forensics."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.utils import ensure_dir, safe_float
from shared.db import close_pool, init_pool
from weather.config import QUOTES_STALE_SECONDS, W1_MAX_SPREAD
from weather.models import WeatherBucketMarket, WeatherMarketContext
from weather.storage import fetch_active_weather_contexts

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper scan current weather markets for merge candidates")
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--profile", type=str, help="Polymarket profile name, for example ColdMath")
    identity_group.add_argument("--wallet", type=str, help="Proxy wallet address to analyze")
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Optional explicit path to wallet_inventory_rebalancing_merge_backtest_bot_config.json",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Artifact output directory")
    parser.add_argument("--watch", action="store_true", help="Poll continuously instead of running a single scan")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help="Seconds to wait between watch-mode scans",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Optional watch-mode scan cap for smoke tests or short sessions",
    )
    parser.add_argument(
        "--exit-on-candidate",
        action="store_true",
        help="Stop watch mode as soon as a live candidate appears",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        result = run_paper_scan(args)
    except KeyboardInterrupt:
        print("Paper scan watch stopped by operator.", flush=True)
        return 130
    logger.info(
        "Paper scan complete for %s with %d candidates and %d near misses",
        result["target"]["proxy_wallet"],
        result["candidate_count"],
        result["near_miss_count"],
    )
    return 0


def run_paper_scan(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    prepared = _prepare_paper_scan(args)
    if args.watch:
        return _run_paper_scan_watch(args, prepared)
    return _run_prepared_paper_scan(prepared)


def _prepare_paper_scan(args: argparse.Namespace) -> dict[str, Any]:
    client = WalletForensicsClient()
    try:
        target = _resolve_target(client, args)
        output_dir = _resolve_output_dir(args, target)
        config_path = _resolve_config_path(args, target, output_dir)
        bot_config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return {
            "target": target,
            "output_dir": output_dir,
            "config_path": config_path,
            "bot_config": bot_config,
        }
    finally:
        client.close()


def _run_prepared_paper_scan(prepared: dict[str, Any]) -> dict[str, Any]:
    target = prepared["target"]
    output_dir = prepared["output_dir"]
    config_path = prepared["config_path"]
    bot_config = prepared["bot_config"]
    scan_report = asyncio.run(scan_inventory_merge_live_report(bot_config=bot_config))
    export_paper_scan_artifacts(
        output_dir=output_dir,
        target=target,
        bot_config=bot_config,
        scan_report=scan_report,
    )
    return {
        "target": target,
        "output_dir": str(output_dir),
        "config_path": str(config_path),
        "bot_config": bot_config,
        "scan_report": scan_report,
        "candidate_count": scan_report["candidate_count"],
        "near_miss_count": len(scan_report.get("near_misses") or []),
    }


def _run_paper_scan_watch(args: argparse.Namespace, prepared: dict[str, Any]) -> dict[str, Any]:
    interval_seconds = float(args.interval_seconds)
    if interval_seconds <= 0:
        raise RuntimeError("--interval-seconds must be greater than zero")
    max_iterations = args.max_iterations
    if max_iterations is not None and int(max_iterations) <= 0:
        raise RuntimeError("--max-iterations must be greater than zero when provided")

    history_path = Path(prepared["output_dir"]) / "wallet_inventory_rebalancing_merge_paper_scan_history.jsonl"
    last_result: dict[str, Any] | None = None
    iterations = 0
    stopped_reason = "operator_stopped"

    while True:
        iterations += 1
        result = _run_prepared_paper_scan(prepared)
        _append_paper_scan_history(history_path=history_path, iteration=iterations, result=result)
        print(_build_watch_status_line(iteration=iterations, result=result), flush=True)
        last_result = result

        if bool(args.exit_on_candidate) and int(result["candidate_count"]) > 0:
            stopped_reason = "candidate_found"
            break
        if max_iterations is not None and iterations >= int(max_iterations):
            stopped_reason = "max_iterations_reached"
            break
        time.sleep(interval_seconds)

    return {
        **(last_result or {}),
        "watch_mode": True,
        "iterations": iterations,
        "history_path": str(history_path),
        "stopped_reason": stopped_reason,
    }


def build_inventory_merge_live_rules(bot_config: dict[str, Any]) -> dict[str, Any]:
    entry_rule = bot_config.get("entry_rule") or {}
    inventory_rule = bot_config.get("inventory_balancing_rule") or {}
    risk_rule = bot_config.get("risk_rule") or {}
    exit_rule = bot_config.get("exit_rule") or {}

    require_full_quote_pair = bool(
        entry_rule.get("require_full_buy_fill_context")
        or risk_rule.get("reject_missing_fill_context")
    )
    min_under_par_buy_fill_ratio = safe_float(entry_rule.get("min_under_par_buy_fill_ratio"))
    midpoint_confirmation_required = bool(
        require_full_quote_pair
        or (min_under_par_buy_fill_ratio is not None and min_under_par_buy_fill_ratio >= 0.5)
    )

    return {
        "strategy_name": bot_config.get("strategy_name") or "inventory_rebalancing_merge",
        "complete_set_cost_lte": safe_float(entry_rule.get("complete_set_cost_lte")) or 1.0,
        "max_inventory_imbalance_ratio": safe_float(
            inventory_rule.get("max_inventory_imbalance_ratio")
            or entry_rule.get("max_inventory_imbalance_ratio")
        ),
        "min_matched_size": safe_float(entry_rule.get("min_matched_size")) or 0.0,
        "max_quote_age_seconds": QUOTES_STALE_SECONDS,
        "max_leg_spread": W1_MAX_SPREAD,
        "require_full_quote_pair": require_full_quote_pair,
        "midpoint_confirmation_required": midpoint_confirmation_required,
        "min_under_par_buy_fill_ratio": min_under_par_buy_fill_ratio,
        "max_worse_buy_fill_ratio": safe_float(entry_rule.get("max_worse_buy_fill_ratio")),
        "worse_buy_override_complete_set_cost_lte": safe_float(
            entry_rule.get("worse_buy_override_complete_set_cost_lte")
        ),
        "preferred_price_history_execution_labels": entry_rule.get("preferred_price_history_execution_labels") or [],
        "max_merge_delay_minutes": safe_float(exit_rule.get("max_merge_delay_minutes")),
    }


async def scan_inventory_merge_live_report(
    *,
    bot_config: dict[str, Any],
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    live_rules = build_inventory_merge_live_rules(bot_config)
    captured_at = captured_at or datetime.now(UTC)
    await init_pool()
    contexts = await fetch_active_weather_contexts(eligible_only=True)
    market_count = sum(len(context.markets) for context in contexts)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    try:
        for context in contexts:
            for market in context.markets:
                row = _evaluate_inventory_merge_candidate(
                    context=context,
                    market=market,
                    live_rules=live_rules,
                    captured_at=captured_at,
                )
                if row["qualifies"]:
                    candidates.append(row)
                else:
                    rejected.append(row)
    finally:
        await close_pool()

    candidates.sort(key=_candidate_sort_key, reverse=True)
    rejected.sort(key=_near_miss_sort_key, reverse=True)

    rejection_reason_counts: dict[str, int] = defaultdict(int)
    for row in rejected:
        for reason in row.get("rejection_reasons") or []:
            rejection_reason_counts[str(reason)] += 1

    return {
        "generated_at": captured_at.isoformat(),
        "context_count": len(contexts),
        "market_count": market_count,
        "candidate_count": len(candidates),
        "rejected_count": len(rejected),
        "live_rules": live_rules,
        "runtime_only_constraints": _runtime_only_constraints(bot_config, live_rules),
        "candidates": candidates,
        "near_misses": rejected[:20],
        "rejection_reason_counts": [
            {"reason": reason, "count": count}
            for reason, count in sorted(rejection_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


async def scan_inventory_merge_candidates(
    *,
    complete_set_cost_lte: float,
    max_inventory_imbalance_ratio: float | None = None,
    min_matched_size: float = 0.0,
    require_full_quote_pair: bool = False,
    max_quote_age_seconds: float | None = None,
    max_leg_spread: float | None = None,
    midpoint_confirmation_required: bool = False,
    worse_buy_override_complete_set_cost_lte: float | None = None,
    captured_at: datetime | None = None,
) -> list[dict[str, Any]]:
    bot_config = {
        "entry_rule": {
            "complete_set_cost_lte": complete_set_cost_lte,
            "min_matched_size": min_matched_size,
            "require_full_buy_fill_context": require_full_quote_pair,
            "worse_buy_override_complete_set_cost_lte": worse_buy_override_complete_set_cost_lte,
        },
        "inventory_balancing_rule": {
            "max_inventory_imbalance_ratio": max_inventory_imbalance_ratio,
        },
        "risk_rule": {
            "reject_missing_fill_context": require_full_quote_pair,
        },
    }
    live_rules = build_inventory_merge_live_rules(bot_config)
    live_rules["max_quote_age_seconds"] = max_quote_age_seconds
    live_rules["max_leg_spread"] = max_leg_spread
    live_rules["midpoint_confirmation_required"] = midpoint_confirmation_required
    if worse_buy_override_complete_set_cost_lte is not None:
        live_rules["worse_buy_override_complete_set_cost_lte"] = worse_buy_override_complete_set_cost_lte

    captured_at = captured_at or datetime.now(UTC)
    await init_pool()
    contexts = await fetch_active_weather_contexts(eligible_only=True)
    try:
        candidates: list[dict[str, Any]] = []
        for context in contexts:
            for market in context.markets:
                row = _evaluate_inventory_merge_candidate(
                    context=context,
                    market=market,
                    live_rules=live_rules,
                    captured_at=captured_at,
                )
                if row["qualifies"]:
                    candidates.append(row)
    finally:
        await close_pool()
    candidates.sort(key=_candidate_sort_key, reverse=True)
    return candidates


def _evaluate_inventory_merge_candidate(
    *,
    context: WeatherMarketContext,
    market: WeatherBucketMarket,
    live_rules: dict[str, Any],
    captured_at: datetime,
) -> dict[str, Any]:
    yes_bid = safe_float(market.yes_bid)
    yes_ask = safe_float(market.yes_ask)
    no_bid = safe_float(market.no_bid)
    no_ask = safe_float(market.no_ask)
    yes_ask_size = safe_float(market.yes_ask_size)
    no_ask_size = safe_float(market.no_ask_size)
    yes_mid = safe_float(market.yes_mid)
    no_mid = safe_float(market.no_mid)
    if yes_mid is None and yes_bid is not None and yes_ask is not None:
        yes_mid = round((yes_bid + yes_ask) / 2.0, 6)
    if no_mid is None and no_bid is not None and no_ask is not None:
        no_mid = round((no_bid + no_ask) / 2.0, 6)

    quote_age_seconds = _quote_age_seconds(market.latest_quote_time, captured_at)
    quote_pair_available = all(value is not None for value in (yes_bid, yes_ask, no_bid, no_ask))
    ask_pair_available = yes_ask is not None and no_ask is not None
    size_pair_available = yes_ask_size is not None and no_ask_size is not None

    combined_cost = _sum_if_all(yes_ask, no_ask)
    combined_mid_cost = _sum_if_all(yes_mid, no_mid)
    merge_edge = round(1.0 - combined_cost, 6) if combined_cost is not None else None
    midpoint_edge = round(1.0 - combined_mid_cost, 6) if combined_mid_cost is not None else None
    max_mergeable_size = min(yes_ask_size, no_ask_size) if size_pair_available else None
    inventory_imbalance_ratio = _imbalance_ratio(yes_ask_size, no_ask_size)
    yes_spread = _quote_spread(yes_bid, yes_ask)
    no_spread = _quote_spread(no_bid, no_ask)
    max_leg_spread = max(
        [value for value in (yes_spread, no_spread) if value is not None],
        default=None,
    )
    quote_quality_label = _quote_quality_label(
        combined_cost=combined_cost,
        combined_mid_cost=combined_mid_cost,
    )

    rejection_reasons: list[str] = []
    if not ask_pair_available:
        rejection_reasons.append("missing_pair_ask")
    if live_rules.get("require_full_quote_pair") and not quote_pair_available:
        rejection_reasons.append("missing_full_quote_pair")
    if quote_age_seconds is None:
        rejection_reasons.append("missing_quote_time")
    else:
        max_quote_age_seconds = safe_float(live_rules.get("max_quote_age_seconds"))
        if max_quote_age_seconds is not None and quote_age_seconds > max_quote_age_seconds:
            rejection_reasons.append("stale_quote")
    if combined_cost is None:
        rejection_reasons.append("missing_complete_set_cost")
    elif combined_cost > float(live_rules["complete_set_cost_lte"]):
        rejection_reasons.append("complete_set_cost_above_threshold")
    if max_mergeable_size is None:
        rejection_reasons.append("missing_mergeable_size")
    elif max_mergeable_size < float(live_rules.get("min_matched_size") or 0.0):
        rejection_reasons.append("insufficient_mergeable_size")
    max_inventory_imbalance_ratio = safe_float(live_rules.get("max_inventory_imbalance_ratio"))
    if max_inventory_imbalance_ratio is not None:
        if inventory_imbalance_ratio is None:
            rejection_reasons.append("missing_inventory_balance")
        elif inventory_imbalance_ratio > max_inventory_imbalance_ratio:
            rejection_reasons.append("inventory_size_imbalance")
    max_allowed_spread = safe_float(live_rules.get("max_leg_spread"))
    if max_allowed_spread is not None:
        if max_leg_spread is None:
            rejection_reasons.append("missing_leg_spread")
        elif max_leg_spread > max_allowed_spread:
            rejection_reasons.append("wide_leg_spread")
    if bool(live_rules.get("midpoint_confirmation_required")):
        if combined_mid_cost is None:
            rejection_reasons.append("missing_midpoint_confirmation")
        elif combined_mid_cost >= 1.0:
            override_cost = safe_float(live_rules.get("worse_buy_override_complete_set_cost_lte"))
            if override_cost is None or combined_cost is None or combined_cost > override_cost:
                rejection_reasons.append("no_midpoint_under_par_confirmation")

    row = {
        "event_id": context.event_id,
        "event_slug": context.event_slug,
        "city": context.city,
        "local_date": context.local_date.isoformat() if context.local_date else None,
        "market_id": market.market_id,
        "market_slug": market.market_slug,
        "yes_token_id": market.yes_token_id,
        "no_token_id": market.no_token_id,
        "neg_risk": bool(market.neg_risk),
        "bucket_label": market.bucket_label,
        "question": market.question,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_mid": yes_mid,
        "yes_ask_size": yes_ask_size,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "no_mid": no_mid,
        "no_ask_size": no_ask_size,
        "combined_cost": combined_cost,
        "combined_mid_cost": combined_mid_cost,
        "merge_edge": merge_edge,
        "midpoint_edge": midpoint_edge,
        "max_mergeable_size": max_mergeable_size,
        "inventory_imbalance_ratio": inventory_imbalance_ratio,
        "yes_spread": yes_spread,
        "no_spread": no_spread,
        "max_leg_spread": max_leg_spread,
        "quote_age_seconds": quote_age_seconds,
        "quote_pair_available": quote_pair_available,
        "quote_quality_label": quote_quality_label,
        "latest_quote_time": market.latest_quote_time.isoformat() if market.latest_quote_time else None,
        "qualifies": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
    }
    return row


def export_paper_scan_artifacts(
    *,
    output_dir: Path,
    target: dict[str, Any],
    bot_config: dict[str, Any],
    scan_report: dict[str, Any],
) -> None:
    import pandas as pd

    ensure_dir(output_dir)
    base_name = "wallet_inventory_rebalancing_merge_paper_scan"
    pd.DataFrame(scan_report.get("candidates") or []).to_csv(output_dir / f"{base_name}.csv", index=False)
    pd.DataFrame(scan_report.get("near_misses") or []).to_csv(
        output_dir / f"{base_name}_near_misses.csv",
        index=False,
    )
    (output_dir / f"{base_name}_summary.json").write_text(
        json.dumps(scan_report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / f"{base_name}.md").write_text(
        build_paper_scan_markdown(
            target=target,
            bot_config=bot_config,
            candidates=scan_report.get("candidates") or [],
            scan_report=scan_report,
        ),
        encoding="utf-8",
    )


def _append_paper_scan_history(
    *,
    history_path: Path,
    iteration: int,
    result: dict[str, Any],
) -> None:
    scan_report = result.get("scan_report") or {}
    candidates = scan_report.get("candidates") or []
    top_candidate = candidates[0] if candidates else None
    entry = {
        "iteration": iteration,
        "generated_at": scan_report.get("generated_at"),
        "proxy_wallet": (result.get("target") or {}).get("proxy_wallet"),
        "strategy_name": (result.get("bot_config") or {}).get("strategy_name"),
        "context_count": scan_report.get("context_count"),
        "market_count": scan_report.get("market_count"),
        "candidate_count": result.get("candidate_count"),
        "near_miss_count": result.get("near_miss_count"),
        "top_rejection_reasons": (scan_report.get("rejection_reason_counts") or [])[:3],
        "top_candidate": {
            "city": top_candidate.get("city"),
            "local_date": top_candidate.get("local_date"),
            "bucket_label": top_candidate.get("bucket_label"),
            "combined_cost": top_candidate.get("combined_cost"),
            "merge_edge": top_candidate.get("merge_edge"),
            "max_mergeable_size": top_candidate.get("max_mergeable_size"),
        }
        if top_candidate
        else None,
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def _build_watch_status_line(*, iteration: int, result: dict[str, Any]) -> str:
    scan_report = result.get("scan_report") or {}
    reasons = scan_report.get("rejection_reason_counts") or []
    top_reason = reasons[0]["reason"] if reasons else "none"
    top_reason_count = reasons[0]["count"] if reasons else 0
    prefix = "ALERT" if int(result.get("candidate_count") or 0) > 0 else "SCAN"
    return (
        f"[{scan_report.get('generated_at') or datetime.now(UTC).isoformat()}] "
        f"{prefix} {iteration}: "
        f"contexts={scan_report.get('context_count', 'n/a')} "
        f"markets={scan_report.get('market_count', 'n/a')} "
        f"candidates={result.get('candidate_count', 0)} "
        f"near_misses={result.get('near_miss_count', 0)} "
        f"top_rejection={top_reason}:{top_reason_count}"
    )


def build_paper_scan_markdown(
    *,
    target: dict[str, Any],
    bot_config: dict[str, Any],
    candidates: list[dict[str, Any]],
    scan_report: dict[str, Any] | None = None,
) -> str:
    threshold = bot_config["entry_rule"]["complete_set_cost_lte"]
    live_rules = (scan_report or {}).get("live_rules") or build_inventory_merge_live_rules(bot_config)
    near_misses = (scan_report or {}).get("near_misses") or []
    rejection_reason_counts = (scan_report or {}).get("rejection_reason_counts") or []
    runtime_only_constraints = (scan_report or {}).get("runtime_only_constraints") or []

    lines = [
        "# Inventory Merge Paper Scan",
        "",
        "## Overview",
        f"- Profile: `{target.get('profile_name') or target['proxy_wallet']}`",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Strategy: `{bot_config.get('strategy_name') or 'inventory_rebalancing_merge'}`",
        f"- Complete set threshold: `{threshold}`",
        f"- Active weather contexts loaded: `{(scan_report or {}).get('context_count', 'n/a')}`",
        f"- Markets evaluated: `{(scan_report or {}).get('market_count', 'n/a')}`",
        f"- Candidate count: `{len(candidates)}`",
    ]
    if scan_report is not None:
        lines.append(f"- Near-miss count tracked: `{len(near_misses)}`")

    lines.extend(
        [
            "",
            "## Active Filters",
            f"- Require full quote pair: `{live_rules.get('require_full_quote_pair')}`",
            f"- Min mergeable size: `{live_rules.get('min_matched_size')}`",
            f"- Max inventory imbalance ratio: `{live_rules.get('max_inventory_imbalance_ratio')}`",
            f"- Max quote age seconds: `{live_rules.get('max_quote_age_seconds')}`",
            f"- Max leg spread: `{live_rules.get('max_leg_spread')}`",
            f"- Midpoint confirmation required: `{live_rules.get('midpoint_confirmation_required')}`",
            "",
            "## Top Candidates",
        ]
    )
    if not candidates:
        lines.append("- No current weather markets satisfy the live merge filters.")
        if scan_report is not None and int(scan_report.get("market_count") or 0) == 0:
            lines.append("- No active eligible weather markets were available in the database snapshot.")
    else:
        for row in candidates[:20]:
            lines.append(
                "- "
                f"`{row['city']}` `{row['local_date']}` `{row['bucket_label']}` | "
                f"ask cost `{row['combined_cost']:.4f}` | mid cost `{_fmt_float(row.get('combined_mid_cost'))}` | "
                f"edge `{row['merge_edge']:.4f}` | size `{_fmt_float(row.get('max_mergeable_size'))}` | "
                f"imbalance `{_fmt_float(row.get('inventory_imbalance_ratio'))}` | "
                f"spread `{_fmt_float(row.get('max_leg_spread'))}` | "
                f"quote age `{_fmt_float(row.get('quote_age_seconds'))}`s | "
                f"quality `{row.get('quote_quality_label')}`"
            )

    lines.extend(["", "## Near Misses"])
    if not near_misses:
        lines.append("- None")
    else:
        for row in near_misses[:10]:
            lines.append(
                "- "
                f"`{row['city']}` `{row['local_date']}` `{row['bucket_label']}` | "
                f"ask cost `{_fmt_float(row.get('combined_cost'))}` | "
                f"size `{_fmt_float(row.get('max_mergeable_size'))}` | "
                f"imbalance `{_fmt_float(row.get('inventory_imbalance_ratio'))}` | "
                f"reasons `{', '.join(row.get('rejection_reasons') or [])}`"
            )

    lines.extend(["", "## Rejection Summary"])
    if not rejection_reason_counts:
        lines.append("- None")
    else:
        for item in rejection_reason_counts[:10]:
            lines.append(f"- `{item['reason']}`: `{item['count']}`")

    lines.extend(["", "## Runtime Notes"])
    if not runtime_only_constraints:
        lines.append("- None")
    else:
        for item in runtime_only_constraints:
            lines.append(f"- {item}")

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


def _resolve_config_path(args: argparse.Namespace, target: dict[str, Any], output_dir: Path) -> Path:
    if args.config_path:
        return Path(args.config_path).resolve()
    default_path = output_dir / "wallet_inventory_rebalancing_merge_backtest_bot_config.json"
    if default_path.exists():
        return default_path
    label = str(target.get("profile_name") or target["proxy_wallet"]).lower().replace("/", "-")
    fallback = Path(__file__).resolve().parents[2] / "results" / "wallet_forensics" / label / default_path.name
    if fallback.exists():
        return fallback
    raise RuntimeError(f"Could not locate bot config for {target['proxy_wallet']}")


def _quote_age_seconds(latest_quote_time: datetime | None, captured_at: datetime) -> float | None:
    if latest_quote_time is None:
        return None
    quote_time = latest_quote_time.astimezone(UTC) if latest_quote_time.tzinfo else latest_quote_time.replace(tzinfo=UTC)
    return round((captured_at - quote_time).total_seconds(), 4)


def _sum_if_all(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left + right, 6)


def _imbalance_ratio(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    total = left + right
    if total <= 0:
        return None
    return round(abs(left - right) / total, 6)


def _quote_spread(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    return round(ask - bid, 6)


def _quote_quality_label(
    *,
    combined_cost: float | None,
    combined_mid_cost: float | None,
) -> str:
    if combined_cost is None:
        return "missing_pair_cost"
    if combined_cost >= 1.0:
        return "not_under_par"
    if combined_mid_cost is None:
        return "ask_only_under_par"
    if combined_mid_cost < 1.0:
        return "mid_confirmed_under_par"
    return "ask_only_under_par"


def _candidate_sort_key(row: dict[str, Any]) -> tuple[float, float, float, float]:
    midpoint_edge = safe_float(row.get("midpoint_edge")) or -999.0
    merge_edge = safe_float(row.get("merge_edge")) or -999.0
    max_mergeable_size = safe_float(row.get("max_mergeable_size")) or 0.0
    spread_penalty = -(safe_float(row.get("max_leg_spread")) or 999.0)
    return (midpoint_edge, merge_edge, max_mergeable_size, spread_penalty)


def _near_miss_sort_key(row: dict[str, Any]) -> tuple[float, float, float, float]:
    merge_edge = safe_float(row.get("merge_edge")) or -999.0
    midpoint_edge = safe_float(row.get("midpoint_edge")) or -999.0
    max_mergeable_size = safe_float(row.get("max_mergeable_size")) or 0.0
    reason_penalty = -float(len(row.get("rejection_reasons") or []))
    return (merge_edge, midpoint_edge, max_mergeable_size, reason_penalty)


def _fmt_float(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.4f}"


def _runtime_only_constraints(bot_config: dict[str, Any], live_rules: dict[str, Any]) -> list[str]:
    entry_rule = bot_config.get("entry_rule") or {}
    notes = [
        "Sequence-level merge delay is still a post-entry runtime concern, not a pre-entry paper-scan filter.",
    ]
    if live_rules.get("preferred_price_history_execution_labels"):
        notes.append(
            "Historical fill-quality labels are approximated live with midpoint confirmation and spread guards, not measured directly."
        )
    if entry_rule.get("max_worse_buy_fill_ratio") is not None:
        notes.append(
            "The historical worse-than-nearby-fill ratio cannot be observed pre-trade; the live scanner uses quote quality proxies instead."
        )
    return notes


if __name__ == "__main__":
    raise SystemExit(main())
