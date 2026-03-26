"""Pure strategy helpers for the dedicated weather merge bot."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from analysis.wallet_forensics.paper_scan import (
    _candidate_sort_key,
    _evaluate_inventory_merge_candidate,
    _near_miss_sort_key,
    build_inventory_merge_live_rules,
)
from analysis.wallet_forensics.utils import safe_float
from weather.models import WeatherMarketContext


@dataclass(slots=True)
class WeatherMergeRuntime:
    strategy_name: str
    live_rules: dict[str, Any]
    sequence_budget_usd: float
    max_total_exposure_usd: float
    daily_loss_limit_usd: float
    min_expected_edge_usd: float
    max_concurrent_positions: int
    partial_repair_window_seconds: float
    min_target_shares: int
    auto_merge: bool


def build_runtime_config(
    bot_config: dict[str, Any],
    *,
    balance_usd: float,
    sequence_budget_cap_usd: float,
    max_total_exposure_cap_usd: float,
    daily_loss_limit_cap_usd: float,
    min_expected_edge_usd: float,
    max_concurrent_positions: int,
    partial_repair_window_seconds: float,
    min_target_shares: int,
    auto_merge: bool,
) -> WeatherMergeRuntime:
    live_rules = build_inventory_merge_live_rules(bot_config)
    if balance_usd > 0:
        if sequence_budget_cap_usd <= 0:
            sequence_budget_usd = max(5.0, min(balance_usd, round(balance_usd * 0.10, 2)))
        else:
            sequence_budget_usd = max(5.0, min(sequence_budget_cap_usd, balance_usd))

        if max_total_exposure_cap_usd <= 0:
            max_total_exposure_usd = round(balance_usd, 2)
        else:
            max_total_exposure_usd = max(
                sequence_budget_usd,
                min(max_total_exposure_cap_usd, round(balance_usd, 2)),
            )

        if daily_loss_limit_cap_usd <= 0:
            daily_loss_limit_usd = round(balance_usd, 2)
        else:
            daily_loss_limit_usd = max(
                sequence_budget_usd,
                min(daily_loss_limit_cap_usd, round(balance_usd, 2)),
            )

        if max_concurrent_positions <= 0:
            runtime_concurrency = max(1, math.floor(max_total_exposure_usd / max(sequence_budget_usd, 0.01)))
        else:
            runtime_concurrency = max_concurrent_positions
    else:
        sequence_budget_usd = 5.0 if sequence_budget_cap_usd <= 0 else sequence_budget_cap_usd
        max_total_exposure_usd = sequence_budget_usd if max_total_exposure_cap_usd <= 0 else max_total_exposure_cap_usd
        daily_loss_limit_usd = max_total_exposure_usd if daily_loss_limit_cap_usd <= 0 else daily_loss_limit_cap_usd
        runtime_concurrency = 1 if max_concurrent_positions <= 0 else max_concurrent_positions

    return WeatherMergeRuntime(
        strategy_name=str(bot_config.get("strategy_name") or "coldmath_inventory_rebalancing_merge_v2"),
        live_rules=live_rules,
        sequence_budget_usd=round(sequence_budget_usd, 2),
        max_total_exposure_usd=round(max_total_exposure_usd, 2),
        daily_loss_limit_usd=round(daily_loss_limit_usd, 2),
        min_expected_edge_usd=round(max(0.0, min_expected_edge_usd), 4),
        max_concurrent_positions=max(1, runtime_concurrency),
        partial_repair_window_seconds=max(0.0, partial_repair_window_seconds),
        min_target_shares=max(1, int(min_target_shares)),
        auto_merge=bool(auto_merge),
    )


def rank_live_candidates(
    contexts: list[WeatherMarketContext],
    runtime: WeatherMergeRuntime,
    *,
    captured_at: datetime | None = None,
    excluded_market_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    report = scan_live_market_report(
        contexts,
        runtime,
        captured_at=captured_at,
        excluded_market_ids=excluded_market_ids,
    )
    return report["candidates"]


def scan_live_market_report(
    contexts: list[WeatherMarketContext],
    runtime: WeatherMergeRuntime,
    *,
    captured_at: datetime | None = None,
    excluded_market_ids: set[str] | None = None,
    near_miss_limit: int = 10,
) -> dict[str, Any]:
    captured_at = captured_at or datetime.now(UTC)
    excluded_market_ids = excluded_market_ids or set()
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    market_count = 0
    rejection_reason_counts: dict[str, int] = {}

    for context in contexts:
        for market in context.markets:
            market_count += 1
            row = _evaluate_inventory_merge_candidate(
                context=context,
                market=market,
                live_rules=runtime.live_rules,
                captured_at=captured_at,
            )
            market_id = str(row.get("market_id") or "")
            if row.get("qualifies"):
                if market_id not in excluded_market_ids:
                    candidates.append(row)
                    continue
                row = {
                    **row,
                    "qualifies": False,
                    "rejection_reasons": ["market_already_active"],
                }
            rejected.append(row)
            for reason in row.get("rejection_reasons") or []:
                reason_key = str(reason)
                rejection_reason_counts[reason_key] = rejection_reason_counts.get(reason_key, 0) + 1

    candidates.sort(key=_candidate_sort_key, reverse=True)
    rejected.sort(key=_near_miss_sort_key, reverse=True)
    return {
        "generated_at": captured_at,
        "context_count": len(contexts),
        "market_count": market_count,
        "candidate_count": len(candidates),
        "near_miss_count": len(rejected),
        "candidates": candidates,
        "cycle_rows": [*candidates, *rejected],
        "near_misses": rejected[: max(0, int(near_miss_limit))],
        "rejection_reason_counts": [
            {"reason": reason, "count": count}
            for reason, count in sorted(
                rejection_reason_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
    }


def plan_entry(
    candidate: dict[str, Any],
    runtime: WeatherMergeRuntime,
    *,
    active_exposure_usd: float,
) -> dict[str, Any] | None:
    combined_cost = safe_float(candidate.get("combined_cost"))
    yes_ask = safe_float(candidate.get("yes_ask"))
    no_ask = safe_float(candidate.get("no_ask"))
    yes_ask_size = safe_float(candidate.get("yes_ask_size"))
    no_ask_size = safe_float(candidate.get("no_ask_size"))
    if (
        combined_cost is None
        or combined_cost <= 0
        or yes_ask is None
        or no_ask is None
        or yes_ask_size is None
        or no_ask_size is None
    ):
        return None

    available_budget = max(0.0, runtime.max_total_exposure_usd - active_exposure_usd)
    sequence_budget = min(runtime.sequence_budget_usd, available_budget)
    if sequence_budget <= 0:
        return None

    max_shares_by_budget = math.floor(sequence_budget / combined_cost)
    max_shares_by_liquidity = math.floor(min(yes_ask_size, no_ask_size))
    target_shares = min(max_shares_by_budget, max_shares_by_liquidity)
    if target_shares < runtime.min_target_shares:
        return None

    expected_edge_per_share = max(0.0, 1.0 - combined_cost)
    expected_edge_usd = round(expected_edge_per_share * target_shares, 6)
    if expected_edge_usd < runtime.min_expected_edge_usd:
        return None

    first_side = "yes" if yes_ask_size <= no_ask_size else "no"
    second_side = "no" if first_side == "yes" else "yes"

    return {
        "strategy_name": runtime.strategy_name,
        "market_id": candidate["market_id"],
        "event_id": candidate["event_id"],
        "event_slug": candidate["event_slug"],
        "city": candidate["city"],
        "local_date": candidate.get("local_date"),
        "bucket_label": candidate["bucket_label"],
        "question": candidate.get("question"),
        "condition_id": candidate["market_id"],
        "neg_risk": bool(candidate.get("neg_risk")),
        "yes_token_id": candidate.get("yes_token_id"),
        "no_token_id": candidate.get("no_token_id"),
        "yes_price": round(yes_ask, 4),
        "no_price": round(no_ask, 4),
        "yes_ask_size": yes_ask_size,
        "no_ask_size": no_ask_size,
        "combined_cost": round(combined_cost, 6),
        "expected_edge_usd": expected_edge_usd,
        "target_shares": target_shares,
        "sequence_budget_usd": round(sequence_budget, 2),
        "first_side": first_side,
        "second_side": second_side,
        "max_second_leg_price": round(runtime.live_rules["complete_set_cost_lte"] - (yes_ask if first_side == "yes" else no_ask), 4),
        "signal_data": {
            "strategy_name": runtime.strategy_name,
            "market_id": candidate["market_id"],
            "event_id": candidate["event_id"],
            "event_slug": candidate["event_slug"],
            "city": candidate["city"],
            "local_date": candidate.get("local_date"),
            "bucket_label": candidate["bucket_label"],
            "combined_cost": round(combined_cost, 6),
            "expected_edge_usd": expected_edge_usd,
            "inventory_imbalance_ratio": candidate.get("inventory_imbalance_ratio"),
            "merge_edge": candidate.get("merge_edge"),
            "quote_quality_label": candidate.get("quote_quality_label"),
            "quote_age_seconds": candidate.get("quote_age_seconds"),
            "target_shares": target_shares,
        },
    }


def compute_mergeable_shares(*, yes_shares: float, no_shares: float) -> int:
    return max(0, math.floor(min(max(0.0, yes_shares), max(0.0, no_shares))))


def open_position_exposure(position: dict[str, Any]) -> float:
    total_entry_cost = safe_float(position.get("total_entry_cost")) or 0.0
    unwind_collateral_usdc = safe_float(position.get("unwind_collateral_usdc")) or 0.0
    merged_collateral_usdc = safe_float(position.get("merged_collateral_usdc")) or 0.0
    redeemed_collateral_usdc = safe_float(position.get("redeemed_collateral_usdc")) or 0.0
    return round(
        max(0.0, total_entry_cost - unwind_collateral_usdc - merged_collateral_usdc - redeemed_collateral_usdc),
        6,
    )
