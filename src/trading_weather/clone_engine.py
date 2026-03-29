"""ColdMath-style multi-playbook weather clone engine."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.wallet_forensics.paper_scan import _evaluate_inventory_merge_candidate
from analysis.wallet_forensics.utils import safe_float
from trading_weather.clone_config import PAIR_PLAYBOOK_KEYS, PLAYBOOK_ORDER, playbook_enabled
from weather.models import WeatherBucketMarket, WeatherMarketContext, complete_neg_risk_quotes


@dataclass(slots=True)
class CloneRuntime:
    strategy_name: str
    config: dict[str, Any]
    runtime: dict[str, Any]
    dry_run: bool
    live_requested: bool


def build_clone_runtime(
    bot_config: dict[str, Any],
    *,
    dry_run: bool,
) -> CloneRuntime:
    return CloneRuntime(
        strategy_name=str(bot_config.get("strategy_name") or "coldmath_weather_clone_v1"),
        config=bot_config,
        runtime=bot_config.get("runtime") or {},
        dry_run=dry_run,
        live_requested=not dry_run,
    )


def _buy_order_size_step(price: float) -> int:
    mills = abs(int(round(float(price) * 1000)))
    if mills <= 0:
        return 1
    return max(1, 10 // math.gcd(mills, 10))


def _normalize_buy_target_shares(price: float, shares: int) -> int:
    if shares <= 0:
        return 0
    step = _buy_order_size_step(price)
    return shares - (shares % step)


def _minimum_buy_target_shares(price: float) -> int:
    step = _buy_order_size_step(price)
    minimum = max(1, math.ceil(1.0 / float(price)))
    remainder = minimum % step
    if remainder == 0:
        return minimum
    return minimum + (step - remainder)


def _normalize_pair_target_shares(yes_price: float, no_price: float, shares: int) -> int:
    if shares <= 0:
        return 0
    step = math.lcm(_buy_order_size_step(yes_price), _buy_order_size_step(no_price))
    return shares - (shares % step)


def _minimum_pair_target_shares(yes_price: float, no_price: float) -> int:
    step = math.lcm(_buy_order_size_step(yes_price), _buy_order_size_step(no_price))
    minimum = max(_minimum_buy_target_shares(yes_price), _minimum_buy_target_shares(no_price))
    remainder = minimum % step
    if remainder == 0:
        return minimum
    return minimum + (step - remainder)


def _is_pair_playbook(playbook_key: str) -> bool:
    return playbook_key in PAIR_PLAYBOOK_KEYS


def _planned_pair_target_shares(plan: dict[str, Any]) -> int:
    yes_target = int(plan.get("yes_target_shares") or 0)
    no_target = int(plan.get("no_target_shares") or 0)
    if yes_target > 0 and no_target > 0:
        return min(yes_target, no_target)
    return int(plan.get("target_shares") or 0)


def _pair_side_targets_from_budget(
    *,
    yes_price: float,
    no_price: float,
    budget: float,
    yes_ask_size: float | None,
    no_ask_size: float | None,
    dominant_leg_budget_fraction: float | None,
) -> tuple[int, int]:
    if budget <= 0:
        return 0, 0
    if dominant_leg_budget_fraction is None:
        target_shares = math.floor(budget / (yes_price + no_price))
        size_cap = min(yes_ask_size, no_ask_size) if yes_ask_size is not None and no_ask_size is not None else None
        if size_cap is not None:
            target_shares = min(target_shares, math.floor(size_cap))
        target_shares = _normalize_pair_target_shares(yes_price, no_price, target_shares)
        return target_shares, target_shares

    dominant_fraction = min(max(float(dominant_leg_budget_fraction), 0.5), 0.995)
    dominant_side = "yes" if yes_price >= no_price else "no"
    dominant_budget = budget * dominant_fraction
    complement_budget = max(0.0, budget - dominant_budget)
    yes_budget = dominant_budget if dominant_side == "yes" else complement_budget
    no_budget = dominant_budget if dominant_side == "no" else complement_budget

    yes_target = _normalize_buy_target_shares(yes_price, math.floor(yes_budget / yes_price))
    no_target = _normalize_buy_target_shares(no_price, math.floor(no_budget / no_price))
    if yes_ask_size is not None:
        yes_target = min(yes_target, math.floor(yes_ask_size))
        yes_target = _normalize_buy_target_shares(yes_price, yes_target)
    if no_ask_size is not None:
        no_target = min(no_target, math.floor(no_ask_size))
        no_target = _normalize_buy_target_shares(no_price, no_target)
    return yes_target, no_target


def preflight_clone_health(clob, *, dry_run: bool) -> dict[str, Any]:
    execution_auth = {
        "status": "unknown",
        "reason": "dry_run" if dry_run else "not_checked",
        "allowed": dry_run,
    }
    if not dry_run:
        try:
            creds = clob.get_api_keys()
            execution_auth = {
                "status": "healthy",
                "reason": "ok",
                "allowed": True,
                "keys_present": bool(creds),
            }
        except Exception as exc:
            execution_auth = {
                "status": "unhealthy",
                "reason": f"{type(exc).__name__}: {exc}",
                "allowed": False,
            }
    return {
        "execution_auth": execution_auth,
        "market_data": {"status": "unknown", "reason": "not_checked"},
        "quote_coverage_ratio": 0.0,
        "quote_pair_markets": 0,
        "total_markets": 0,
        "direct_quote_markets": 0,
        "direct_quote_tokens": 0,
        "execution_allowed": bool(execution_auth.get("allowed")),
    }


def refresh_contexts_with_direct_quotes(
    clob,
    contexts: list[WeatherMarketContext],
    *,
    captured_at: datetime,
    health_config: dict[str, Any],
) -> dict[str, Any]:
    if not bool(health_config.get("direct_quote_fallback_enabled", True)):
        return {
            "quote_pair_markets": _count_quote_pair_markets(contexts),
            "total_markets": sum(len(context.markets) for context in contexts),
            "direct_quote_markets": 0,
            "direct_quote_tokens": 0,
            "book_errors": [],
        }

    max_age = float(health_config.get("direct_quote_max_age_seconds") or 20.0)
    max_markets = max(0, int(health_config.get("max_direct_quote_markets_per_cycle") or 0))
    selected_markets: list[WeatherBucketMarket] = []
    for context in contexts:
        for market in context.markets:
            if len(selected_markets) >= max_markets:
                break
            if _needs_direct_quote_refresh(market, captured_at=captured_at, max_age=max_age):
                selected_markets.append(market)
        if len(selected_markets) >= max_markets:
            break

    token_market_map: dict[str, tuple[WeatherBucketMarket, str]] = {}
    params = []
    if selected_markets:
        from py_clob_client.clob_types import BookParams

        for market in selected_markets:
            if market.yes_token_id:
                token_market_map[str(market.yes_token_id)] = (market, "yes")
                params.append(BookParams(token_id=str(market.yes_token_id)))
            if market.no_token_id:
                token_market_map[str(market.no_token_id)] = (market, "no")
                params.append(BookParams(token_id=str(market.no_token_id)))

    book_errors: list[str] = []
    direct_quote_tokens = 0
    if params:
        try:
            summaries = clob.get_order_books(params)
        except Exception as exc:
            summaries = []
            book_errors.append(f"{type(exc).__name__}: {exc}")
        for summary in summaries or []:
            token_id = str(getattr(summary, "asset_id", "") or getattr(summary, "token_id", "") or "")
            mapping = token_market_map.get(token_id)
            if not mapping:
                continue
            market, side = mapping
            _apply_order_book_summary(market, side=side, summary=summary, captured_at=captured_at)
            direct_quote_tokens += 1

    total_markets = sum(len(context.markets) for context in contexts)
    quote_pair_markets = _count_quote_pair_markets(contexts)
    return {
        "quote_pair_markets": quote_pair_markets,
        "total_markets": total_markets,
        "direct_quote_markets": len(selected_markets),
        "direct_quote_tokens": direct_quote_tokens,
        "book_errors": book_errors,
    }


def evaluate_clone_cycle(
    *,
    contexts: list[WeatherMarketContext],
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
    active_positions: list[dict[str, Any]] | None = None,
    active_market_ids: set[str] | None = None,
) -> dict[str, Any]:
    active_positions = active_positions or []
    active_market_ids = active_market_ids or set()
    playbooks = runtime.config.get("playbooks") or {}
    cycle_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    sequence_snapshots: list[dict[str, Any]] = []
    market_count = 0
    top_rejection_counts: dict[str, int] = {}

    context_bucket_extremes = {context.event_id: _bucket_extremes(context) for context in contexts}
    directional_ranges = {context.event_id: _directional_side_ranges(context) for context in contexts}

    for context in contexts:
        for market in context.markets:
            market_count += 1
            rows_for_market: list[dict[str, Any]] = []
            rows_for_market.append(
                _evaluate_paired_under_par(
                    context=context,
                    market=market,
                    playbook_key="paired_under_par",
                    playbook=playbooks.get("paired_under_par") or {},
                    runtime=runtime,
                    captured_at=captured_at,
                    health_state=health_state,
                    sequence_state=sequence_state,
                    active_market_ids=active_market_ids,
                )
            )
            rows_for_market.append(
                _evaluate_paired_under_par(
                    context=context,
                    market=market,
                    playbook_key="asymmetric_paired_accumulation",
                    playbook=playbooks.get("asymmetric_paired_accumulation") or {},
                    runtime=runtime,
                    captured_at=captured_at,
                    health_state=health_state,
                    sequence_state=sequence_state,
                    active_market_ids=active_market_ids,
                )
            )
            rows_for_market.extend(
                _evaluate_directional_playbook(
                    context=context,
                    market=market,
                    playbook_key="cheap_bucket_accumulation",
                    playbook=playbooks.get("cheap_bucket_accumulation") or {},
                    runtime=runtime,
                    captured_at=captured_at,
                    health_state=health_state,
                    sequence_state=sequence_state,
                    extremes=context_bucket_extremes.get(context.event_id) or {},
                    directional_ranges=directional_ranges.get(context.event_id) or {},
                )
            )
            rows_for_market.extend(
                _evaluate_directional_playbook(
                    context=context,
                    market=market,
                    playbook_key="tail_bucket_accumulation",
                    playbook=playbooks.get("tail_bucket_accumulation") or {},
                    runtime=runtime,
                    captured_at=captured_at,
                    health_state=health_state,
                    sequence_state=sequence_state,
                    extremes=context_bucket_extremes.get(context.event_id) or {},
                    directional_ranges=directional_ranges.get(context.event_id) or {},
                )
            )
            rows_for_market.extend(
                _evaluate_directional_playbook(
                    context=context,
                    market=market,
                    playbook_key="high_prob_bucket_accumulation",
                    playbook=playbooks.get("high_prob_bucket_accumulation") or {},
                    runtime=runtime,
                    captured_at=captured_at,
                    health_state=health_state,
                    sequence_state=sequence_state,
                    extremes=context_bucket_extremes.get(context.event_id) or {},
                    directional_ranges=directional_ranges.get(context.event_id) or {},
                )
            )
            for row in rows_for_market:
                cycle_rows.append(row)
                sequence_snapshots.append(row["sequence_data"])
                if row["qualifies"]:
                    candidates.append(row)
                else:
                    for reason in row.get("rejection_reasons") or []:
                        top_rejection_counts[str(reason)] = top_rejection_counts.get(str(reason), 0) + 1
        basket_rows = _evaluate_neg_risk_basket_playbook(
            context=context,
            playbook=playbooks.get("neg_risk_basket") or {},
            runtime=runtime,
            captured_at=captured_at,
            health_state=health_state,
            sequence_state=sequence_state,
        )
        for row in basket_rows:
            cycle_rows.append(row)
            sequence_snapshots.append(row["sequence_data"])
            if row["qualifies"]:
                candidates.append(row)
            else:
                for reason in row.get("rejection_reasons") or []:
                    top_rejection_counts[str(reason)] = top_rejection_counts.get(str(reason), 0) + 1

    exit_rows = _evaluate_inventory_closeout_playbook(
        runtime=runtime,
        captured_at=captured_at,
        health_state=health_state,
        sequence_state=sequence_state,
        active_positions=active_positions,
    )
    for row in exit_rows:
        cycle_rows.append(row)
        sequence_snapshots.append(row["sequence_data"])
        if row["qualifies"]:
            candidates.append(row)
        else:
            for reason in row.get("rejection_reasons") or []:
                top_rejection_counts[str(reason)] = top_rejection_counts.get(str(reason), 0) + 1

    candidates.sort(key=_candidate_sort_key, reverse=True)
    top_rejection_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(top_rejection_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "captured_at": captured_at,
        "context_count": len(contexts),
        "market_count": market_count,
        "cycle_rows": cycle_rows,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "top_rejection_reasons": top_rejection_reasons[:10],
        "sequence_snapshots": sequence_snapshots,
    }


def plan_paired_entry(
    candidate: dict[str, Any],
    runtime: CloneRuntime,
    *,
    active_exposure_usd: float,
) -> dict[str, Any] | None:
    playbook_key = str(candidate.get("playbook_key") or "")
    combined_cost = safe_float(candidate.get("combined_cost"))
    yes_ask = safe_float(candidate.get("yes_ask"))
    no_ask = safe_float(candidate.get("no_ask"))
    yes_ask_size = safe_float(candidate.get("yes_ask_size"))
    no_ask_size = safe_float(candidate.get("no_ask_size"))
    if (
        not _is_pair_playbook(playbook_key)
        or combined_cost is None
        or yes_ask is None
        or no_ask is None
        or combined_cost <= 0
    ):
        return None

    playbook = ((runtime.config.get("playbooks") or {}).get(playbook_key) or {})
    playbook_budget = float(playbook.get("sequence_budget_usd") or runtime.runtime.get("sequence_budget_usd") or 0.0)
    budget = max(
        0.0,
        min(
            playbook_budget,
            float(runtime.runtime.get("max_total_exposure_usd") or 0.0) - active_exposure_usd,
        ),
    )
    if budget <= 0:
        return None
    dominant_leg_budget_fraction = None
    if playbook_key == "asymmetric_paired_accumulation":
        dominant_leg_budget_fraction = safe_float(playbook.get("dominant_leg_budget_fraction")) or 0.94
    yes_target_shares, no_target_shares = _pair_side_targets_from_budget(
        yes_price=yes_ask,
        no_price=no_ask,
        budget=budget,
        yes_ask_size=yes_ask_size,
        no_ask_size=no_ask_size,
        dominant_leg_budget_fraction=dominant_leg_budget_fraction,
    )
    min_pair_target = max(
        1,
        int(runtime.runtime.get("min_target_shares") or 1),
        _minimum_pair_target_shares(yes_ask, no_ask),
    )
    if playbook_key == "asymmetric_paired_accumulation":
        if yes_target_shares < max(1, _minimum_buy_target_shares(yes_ask)):
            return None
        if no_target_shares < max(1, _minimum_buy_target_shares(no_ask)):
            return None
    else:
        if yes_target_shares < min_pair_target or no_target_shares < min_pair_target:
            return None
    paired_target_shares = min(yes_target_shares, no_target_shares)
    if paired_target_shares <= 0:
        return None
    threshold = float(playbook.get("synthetic_pair_cost_lte") or 1.0)
    edge_per_share = max(0.0, max(1.0, threshold) - combined_cost)
    expected_edge_usd = round(edge_per_share * paired_target_shares, 6)
    if expected_edge_usd < float(runtime.runtime.get("min_expected_edge_usd") or 0.0):
        return None
    yes_notional = round(yes_ask * yes_target_shares, 6)
    no_notional = round(no_ask * no_target_shares, 6)
    if yes_notional <= no_notional:
        first_side = "yes"
    else:
        first_side = "no"
    second_side = "no" if first_side == "yes" else "yes"
    total_target_cost = round(yes_notional + no_notional, 6)
    return {
        "playbook_key": playbook_key,
        "strategy_name": runtime.strategy_name,
        "market_id": candidate["market_id"],
        "event_id": candidate["event_id"],
        "event_slug": candidate["event_slug"],
        "city": candidate["city"],
        "local_date": candidate.get("local_date"),
        "bucket_label": candidate["bucket_label"],
        "condition_id": candidate["market_id"],
        "neg_risk": bool(candidate.get("neg_risk")),
        "yes_token_id": candidate.get("yes_token_id"),
        "no_token_id": candidate.get("no_token_id"),
        "yes_price": round(yes_ask, 4),
        "no_price": round(no_ask, 4),
        "yes_ask_size": yes_ask_size,
        "no_ask_size": no_ask_size,
        "combined_cost": round(combined_cost, 6),
        "target_shares": paired_target_shares,
        "yes_target_shares": yes_target_shares,
        "no_target_shares": no_target_shares,
        "total_target_cost": total_target_cost,
        "expected_edge_usd": expected_edge_usd,
        "signal_score": safe_float(candidate.get("candidate_score")) or 0.0,
        "sequence_budget_usd": round(budget, 2),
        "first_side": first_side,
        "second_side": second_side,
        "signal_data": candidate.get("signal_data") or {},
        "sequence_data": candidate.get("sequence_data") or {},
        "quote_snapshot": candidate.get("quote_snapshot") or {},
    }


def plan_neg_risk_entry(
    candidate: dict[str, Any],
    runtime: CloneRuntime,
    *,
    active_exposure_usd: float,
) -> dict[str, Any] | None:
    if str(candidate.get("playbook_key") or "") != "neg_risk_basket":
        return None
    side = str(candidate.get("side") or "").lower()
    if side not in {"yes", "no"}:
        return None
    basket_legs = list((candidate.get("signal_data") or {}).get("selected_legs") or [])
    if not basket_legs:
        return None

    playbook = ((runtime.config.get("playbooks") or {}).get("neg_risk_basket") or {})
    playbook_budget = float(playbook.get("sequence_budget_usd") or runtime.runtime.get("sequence_budget_usd") or 0.0)
    available_budget = max(0.0, float(runtime.runtime.get("max_total_exposure_usd") or 0.0) - active_exposure_usd)
    budget = max(0.0, min(playbook_budget, available_budget))
    if budget <= 0:
        return None

    per_leg_budget = budget / max(len(basket_legs), 1)
    planned_legs: list[dict[str, Any]] = []
    min_target_shares = max(1, int(runtime.runtime.get("min_target_shares") or 1))
    for leg in basket_legs:
        price = safe_float(leg.get("price"))
        if price is None or price <= 0:
            continue
        available_size = safe_float(leg.get("ask_size"))
        target_shares = math.floor(per_leg_budget / price)
        if available_size is not None and available_size > 0:
            target_shares = min(target_shares, math.floor(available_size))
        target_shares = _normalize_buy_target_shares(price, target_shares)
        if target_shares < max(min_target_shares, _minimum_buy_target_shares(price)):
            continue
        planned_legs.append(
            {
                "market_id": str(leg.get("market_id") or ""),
                "bucket_label": str(leg.get("bucket_label") or ""),
                "token_id": str(leg.get("token_id") or ""),
                "price": round(price, 6),
                "available_size": available_size,
                "target_shares": int(target_shares),
            }
        )
    if len(planned_legs) < int(playbook.get("min_distinct_conditions") or 3):
        return None

    total_target_cost = round(sum(float(leg["price"]) * float(leg["target_shares"]) for leg in planned_legs), 6)
    basket_cost = safe_float(candidate.get("combined_cost")) or 0.0
    threshold = float(playbook.get("synthetic_basket_cost_lte") or 0.99)
    expected_edge_usd = round(max(0.0, threshold - basket_cost) * min(leg["target_shares"] for leg in planned_legs), 6)
    if expected_edge_usd < float(runtime.runtime.get("min_expected_edge_usd") or 0.0):
        return None

    return {
        "playbook_key": "neg_risk_basket",
        "strategy_name": runtime.strategy_name,
        "market_id": candidate["market_id"],
        "event_id": candidate["event_id"],
        "event_slug": candidate["event_slug"],
        "city": candidate["city"],
        "local_date": candidate.get("local_date"),
        "bucket_label": candidate["bucket_label"],
        "condition_id": candidate["condition_id"],
        "neg_risk": True,
        "side": side,
        "legs": planned_legs,
        "target_shares": sum(int(leg["target_shares"]) for leg in planned_legs),
        "selected_condition_count": len(planned_legs),
        "combined_cost": round(basket_cost, 6),
        "total_target_cost": total_target_cost,
        "expected_edge_usd": expected_edge_usd,
        "signal_score": safe_float(candidate.get("candidate_score")) or 0.0,
        "sequence_budget_usd": round(budget, 2),
        "signal_data": candidate.get("signal_data") or {},
        "sequence_data": candidate.get("sequence_data") or {},
        "quote_snapshot": candidate.get("quote_snapshot") or {},
    }


def plan_directional_entry(
    candidate: dict[str, Any],
    runtime: CloneRuntime,
    *,
    active_exposure_usd: float,
) -> dict[str, Any] | None:
    playbook_key = str(candidate.get("playbook_key") or "")
    if playbook_key not in {"cheap_bucket_accumulation", "tail_bucket_accumulation", "high_prob_bucket_accumulation"}:
        return None
    side = str(candidate.get("side") or "").lower()
    if side not in {"yes", "no"}:
        return None

    quote_snapshot = candidate.get("quote_snapshot") or {}
    price = safe_float(candidate.get("directional_price"))
    if price is None or price <= 0:
        return None
    token_id = candidate.get("yes_token_id") if side == "yes" else candidate.get("no_token_id")
    available_size = safe_float(
        quote_snapshot.get("yes_ask_size") if side == "yes" else quote_snapshot.get("no_ask_size")
    )

    playbook = ((runtime.config.get("playbooks") or {}).get(playbook_key) or {})
    playbook_budget = float(playbook.get("sequence_budget_usd") or runtime.runtime.get("sequence_budget_usd") or 0.0)
    available_budget = max(0.0, float(runtime.runtime.get("max_total_exposure_usd") or 0.0) - active_exposure_usd)
    budget = max(0.0, min(playbook_budget, available_budget))
    if budget <= 0:
        return None

    target_shares = math.floor(budget / price)
    if available_size is not None and available_size > 0:
        target_shares = min(target_shares, math.floor(available_size))
    target_shares = _normalize_buy_target_shares(price, target_shares)
    min_target_shares = max(
        1,
        int(runtime.runtime.get("min_target_shares") or 1),
        _minimum_buy_target_shares(price),
    )
    if target_shares < min_target_shares:
        return None

    profit_take_price = safe_float(playbook.get("profit_take_price"))
    minimum_hold_seconds = safe_float(playbook.get("minimum_hold_seconds")) or 0.0
    expected_edge_usd = 0.0
    if profit_take_price is not None and profit_take_price > price:
        expected_edge_usd = round((profit_take_price - price) * target_shares, 6)
    else:
        expected_edge_usd = round(price * target_shares * 0.1, 6)
    if expected_edge_usd < float(runtime.runtime.get("min_expected_edge_usd") or 0.0):
        return None

    return {
        "playbook_key": playbook_key,
        "strategy_name": runtime.strategy_name,
        "market_id": candidate["market_id"],
        "event_id": candidate["event_id"],
        "event_slug": candidate["event_slug"],
        "city": candidate["city"],
        "local_date": candidate.get("local_date"),
        "bucket_label": candidate["bucket_label"],
        "condition_id": candidate["market_id"],
        "neg_risk": bool(candidate.get("neg_risk")),
        "yes_token_id": candidate.get("yes_token_id"),
        "no_token_id": candidate.get("no_token_id"),
        "side": side,
        "token_id": token_id,
        "price": round(price, 4),
        "available_size": available_size,
        "target_shares": target_shares,
        "expected_edge_usd": expected_edge_usd,
        "signal_score": safe_float(candidate.get("candidate_score")) or 0.0,
        "sequence_budget_usd": round(budget, 2),
        "profit_take_price": profit_take_price,
        "minimum_hold_seconds": minimum_hold_seconds,
        "signal_data": candidate.get("signal_data") or {},
        "sequence_data": candidate.get("sequence_data") or {},
        "quote_snapshot": quote_snapshot,
    }


def build_clone_cycle_summary(
    *,
    report: dict[str, Any],
    health_state: dict[str, Any],
    active_positions: list[dict[str, Any]],
    entry_attempts: int,
) -> dict[str, Any]:
    top_candidate = report["candidates"][0] if report["candidates"] else None
    return {
        "captured_at": report["captured_at"].isoformat(),
        "execution_allowed": bool(health_state.get("execution_allowed")),
        "execution_health": (health_state.get("execution_auth") or {}).get("status"),
        "market_data_health": (health_state.get("market_data") or {}).get("status"),
        "quote_coverage_ratio": round(float(health_state.get("quote_coverage_ratio") or 0.0), 6),
        "context_count": int(report.get("context_count") or 0),
        "market_count": int(report.get("market_count") or 0),
        "candidate_count": int(report.get("candidate_count") or 0),
        "sequence_count": len(report.get("sequence_snapshots") or []),
        "entry_attempts": int(entry_attempts),
        "active_positions": len(active_positions),
        "top_candidate": {
            "playbook_key": top_candidate.get("playbook_key"),
            "city": top_candidate.get("city"),
            "local_date": top_candidate.get("local_date"),
            "bucket_label": top_candidate.get("bucket_label"),
            "side": top_candidate.get("side"),
            "candidate_score": top_candidate.get("candidate_score"),
            "combined_cost": top_candidate.get("combined_cost"),
            "directional_price": top_candidate.get("directional_price"),
            "rejection_reasons": top_candidate.get("rejection_reasons"),
        }
        if top_candidate
        else None,
        "top_rejection_reasons": report.get("top_rejection_reasons") or [],
    }


def clone_cycle_status_message(summary: dict[str, Any]) -> str:
    message = (
        "[WEATHER-CLONE] Summary | "
        f"execution_allowed={summary.get('execution_allowed')} "
        f"auth={summary.get('execution_health')} "
        f"market_data={summary.get('market_data_health')} "
        f"quote_coverage={float(summary.get('quote_coverage_ratio') or 0.0):.2f} "
        f"daily_pnl={float(summary.get('daily_realized_pnl') or 0.0):.2f} "
        f"spent={float(summary.get('total_spent_usd') or 0.0):.2f}/{float(summary.get('total_spend_limit_usd') or 0.0):.2f} "
        f"contexts={int(summary.get('context_count') or 0)} "
        f"markets={int(summary.get('market_count') or 0)} "
        f"candidates={int(summary.get('candidate_count') or 0)} "
        f"sequences={int(summary.get('sequence_count') or 0)} "
        f"active_positions={int(summary.get('active_positions') or 0)} "
        f"exposure={float(summary.get('active_exposure_usd') or 0.0):.2f} "
        f"entries={int(summary.get('entry_attempts') or 0)}"
    )
    stand_down_reason = str(summary.get("stand_down_reason") or "").strip()
    if stand_down_reason:
        message += f" | stand_down={stand_down_reason}"
    guard_warning_reason = str(summary.get("guard_warning_reason") or "").strip()
    if guard_warning_reason:
        message += f" | guard_warning={guard_warning_reason}"
    top_candidate = summary.get("top_candidate") or {}
    if top_candidate:
        if top_candidate.get("playbook_key") in {"paired_under_par", "asymmetric_paired_accumulation", "neg_risk_basket"}:
            message += (
                " | top="
                f"{top_candidate.get('playbook_key')} "
                f"{top_candidate.get('city')} {top_candidate.get('bucket_label')} "
                f"cost={(safe_float(top_candidate.get('combined_cost')) or float('nan')):.4f} "
                f"score={(safe_float(top_candidate.get('candidate_score')) or float('nan')):.4f}"
            )
        else:
            message += (
                " | top="
                f"{top_candidate.get('playbook_key')} "
                f"{top_candidate.get('city')} {top_candidate.get('bucket_label')} {top_candidate.get('side')} "
                f"price={(safe_float(top_candidate.get('directional_price')) or float('nan')):.4f} "
                f"score={(safe_float(top_candidate.get('candidate_score')) or float('nan')):.4f}"
            )
    top_reasons = summary.get("top_rejection_reasons") or []
    if top_reasons:
        message += " | rejections=" + ",".join(
            f"{item.get('reason')}:{item.get('count')}" for item in top_reasons[:3]
        )
    return message


def append_clone_cycle_history(*, history_path: Path, event_type: str, payload: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"event_type": event_type, **payload}
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def _count_quote_pair_markets(contexts: list[WeatherMarketContext]) -> int:
    count = 0
    for context in contexts:
        for market in context.markets:
            if market.yes_ask is not None and market.no_ask is not None:
                count += 1
    return count


def _needs_direct_quote_refresh(
    market: WeatherBucketMarket,
    *,
    captured_at: datetime,
    max_age: float,
) -> bool:
    if market.yes_ask is None or market.no_ask is None:
        return True
    if market.latest_quote_time is None:
        return True
    quote_time = market.latest_quote_time.astimezone(UTC) if market.latest_quote_time.tzinfo else market.latest_quote_time.replace(tzinfo=UTC)
    return (captured_at - quote_time).total_seconds() > max_age


def _apply_order_book_summary(
    market: WeatherBucketMarket,
    *,
    side: str,
    summary,
    captured_at: datetime,
) -> None:
    best_bid, best_bid_size = _best_level(getattr(summary, "bids", []), best="max")
    best_ask, best_ask_size = _best_level(getattr(summary, "asks", []), best="min")
    mid = None
    if best_bid is not None and best_ask is not None:
        mid = round((best_bid + best_ask) / 2.0, 6)
    if side == "yes":
        market.yes_bid = best_bid
        market.yes_ask = best_ask
        market.yes_mid = mid
        market.yes_bid_size = best_bid_size
        market.yes_ask_size = best_ask_size
    else:
        market.no_bid = best_bid
        market.no_ask = best_ask
        market.no_mid = mid
        market.no_bid_size = best_bid_size
        market.no_ask_size = best_ask_size
    market.latest_quote_time = _book_timestamp(summary, captured_at)


def _best_level(levels: list[Any], *, best: str) -> tuple[float | None, float | None]:
    if not levels:
        return None, None
    parsed: list[tuple[float, float | None]] = []
    for level in levels:
        price = safe_float(getattr(level, "price", None))
        size = safe_float(getattr(level, "size", None))
        if price is None:
            continue
        parsed.append((price, size))
    if not parsed:
        return None, None
    chosen = max(parsed, key=lambda item: item[0]) if best == "max" else min(parsed, key=lambda item: item[0])
    return chosen


def _book_timestamp(summary, captured_at: datetime) -> datetime:
    raw = getattr(summary, "timestamp", None)
    if raw in (None, ""):
        return captured_at
    number = safe_float(raw)
    if number is not None:
        if number > 10_000_000_000:
            number = number / 1000.0
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return captured_at
    try:
        parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return captured_at


def _evaluate_paired_under_par(
    *,
    context: WeatherMarketContext,
    market: WeatherBucketMarket,
    playbook_key: str,
    playbook: dict[str, Any],
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
    active_market_ids: set[str],
) -> dict[str, Any]:
    yes_bid = safe_float(market.yes_bid)
    yes_ask = safe_float(market.yes_ask)
    no_bid = safe_float(market.no_bid)
    no_ask = safe_float(market.no_ask)
    yes_mid = safe_float(market.yes_mid)
    no_mid = safe_float(market.no_mid)
    yes_ask_size = safe_float(market.yes_ask_size)
    no_ask_size = safe_float(market.no_ask_size)
    combined_cost = (yes_ask + no_ask) if yes_ask is not None and no_ask is not None else None
    combined_mid_cost = (yes_mid + no_mid) if yes_mid is not None and no_mid is not None else None
    quote_age_seconds = _quote_age_seconds(market.latest_quote_time, captured_at)
    max_quote_age_seconds = safe_float(playbook.get("max_quote_age_seconds") or 120.0)
    require_full_quote_pair = bool(
        playbook.get("live_requires_full_quote_pair")
        if runtime.live_requested
        else playbook.get("shadow_requires_full_quote_pair")
    )
    stale_recovery_tolerance = safe_float(playbook.get("stale_pair_recovery_tolerance")) or 0.03
    threshold = safe_float(playbook.get("synthetic_pair_cost_lte")) or 0.995
    effective_threshold = threshold + (stale_recovery_tolerance if bool(playbook.get("allow_stale_pair_recovery", True)) else 0.0)
    max_mergeable_size = (
        min(yes_ask_size, no_ask_size)
        if yes_ask_size is not None and no_ask_size is not None
        else None
    )
    leg_spreads = [
        spread
        for spread in (_quote_spread(yes_bid, yes_ask), _quote_spread(no_bid, no_ask))
        if spread is not None
    ]
    max_leg_spread = max(leg_spreads, default=None)
    rejection_reasons: list[str] = []
    if yes_ask is None or no_ask is None:
        rejection_reasons.append("missing_pair_ask")
    if require_full_quote_pair and any(value is None for value in (yes_bid, yes_ask, no_bid, no_ask)):
        rejection_reasons.append("missing_full_quote_pair")
    if quote_age_seconds is None:
        rejection_reasons.append("missing_quote_time")
    elif max_quote_age_seconds is not None and quote_age_seconds > max_quote_age_seconds:
        rejection_reasons.append("stale_quote")
    if combined_cost is None:
        rejection_reasons.append("missing_complete_set_cost")
    elif combined_cost > effective_threshold:
        rejection_reasons.append("complete_set_cost_above_threshold")
    if combined_mid_cost is None and bool(playbook.get("midpoint_confirmation_required", False)):
        rejection_reasons.append("missing_midpoint_confirmation")
    elif (
        combined_mid_cost is not None
        and bool(playbook.get("midpoint_confirmation_required", False))
        and combined_mid_cost >= 1.0
        and (combined_cost is None or combined_cost > effective_threshold)
    ):
        rejection_reasons.append("no_midpoint_under_par_confirmation")
    configured_max_leg_spread = safe_float(playbook.get("max_leg_spread")) or 0.08
    min_leg_price_gte = safe_float(playbook.get("min_leg_price_gte"))
    max_leg_price_lte = safe_float(playbook.get("max_leg_price_lte"))
    if configured_max_leg_spread is not None:
        if max_leg_spread is None:
            rejection_reasons.append("missing_leg_spread")
        elif max_leg_spread > configured_max_leg_spread:
            rejection_reasons.append("wide_leg_spread")
    leg_prices = [price for price in (yes_ask, no_ask) if price is not None]
    if leg_prices:
        min_leg_price = min(leg_prices)
        max_leg_price = max(leg_prices)
        if min_leg_price_gte is not None and min(leg_prices) < min_leg_price_gte:
            rejection_reasons.append("leg_price_below_floor")
        if max_leg_price_lte is not None and max(leg_prices) > max_leg_price_lte:
            rejection_reasons.append("leg_price_above_ceiling")
        if playbook_key == "asymmetric_paired_accumulation":
            dominant_leg_price_gte = safe_float(playbook.get("dominant_leg_price_gte"))
            complementary_leg_price_lte = safe_float(playbook.get("complementary_leg_price_lte"))
            if dominant_leg_price_gte is not None and max(leg_prices) < dominant_leg_price_gte:
                rejection_reasons.append("leg_price_below_floor")
            if complementary_leg_price_lte is not None and min(leg_prices) > complementary_leg_price_lte:
                rejection_reasons.append("leg_price_above_ceiling")
        else:
            if max_leg_price >= 0.90 and min_leg_price <= 0.10:
                rejection_reasons.append("routed_to_asymmetric_pair_playbook")
    allow_active_market_reentry = bool(playbook.get("allow_active_market_reentry", True))
    if str(market.market_id or "") in active_market_ids and not allow_active_market_reentry:
        rejection_reasons.append("market_already_active")

    qualifies = not rejection_reasons
    merge_edge = round(1.0 - combined_cost, 6) if combined_cost is not None else None
    leg_prices = [price for price in (yes_ask, no_ask) if price is not None]
    min_leg_price = min(leg_prices) if leg_prices else 0.0
    max_leg_price = max(leg_prices) if leg_prices else 1.0
    if playbook_key == "asymmetric_paired_accumulation":
        dominance_multiplier = max(1.0, max_leg_price / max(min_leg_price, 0.001))
        moderation_multiplier = max(1.0, dominance_multiplier)
    else:
        moderation_multiplier = max(1.0, max(0.001, min_leg_price) * max(0.001, 1.0 - max_leg_price) * 10_000.0)
    candidate_score = round(
        max(0.0, effective_threshold - (combined_cost or effective_threshold))
        * max(1.0, max_mergeable_size or 1.0)
        * moderation_multiplier,
        6,
    )
    base = {
        "event_id": context.event_id,
        "event_slug": context.event_slug,
        "city": context.city,
        "local_date": context.local_date,
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
        "midpoint_edge": round(1.0 - combined_mid_cost, 6) if combined_mid_cost is not None else None,
        "max_mergeable_size": max_mergeable_size,
        "inventory_imbalance_ratio": None,
        "yes_spread": _quote_spread(yes_bid, yes_ask),
        "no_spread": _quote_spread(no_bid, no_ask),
        "max_leg_spread": max_leg_spread,
        "quote_age_seconds": quote_age_seconds,
        "quote_pair_available": all(value is not None for value in (yes_bid, yes_ask, no_bid, no_ask)),
        "quote_quality_label": "paired_clone_signal" if qualifies else "paired_clone_watch",
        "latest_quote_time": market.latest_quote_time.isoformat() if market.latest_quote_time else None,
        "qualifies": qualifies,
        "rejection_reasons": rejection_reasons,
    }
    mergeable_size = safe_float(base.get("max_mergeable_size")) or 0.0
    sequence_key = f"{playbook_key}:{market.market_id}"
    sequence = _update_sequence_state(
        sequence_state=sequence_state,
        sequence_key=sequence_key,
        playbook_key=playbook_key,
        market=market,
        context=context,
        side=None,
        captured_at=captured_at,
        rolling_window_seconds=float(playbook.get("rolling_window_seconds") or 60.0),
        qualifies=bool(base.get("qualifies")),
        candidate_score=candidate_score,
        rejection_reasons=base.get("rejection_reasons") or [],
        quote_snapshot=_quote_snapshot(market, captured_at=captured_at),
        signal_data={
            "combined_cost": combined_cost,
            "merge_edge": merge_edge,
            "mergeable_size": mergeable_size,
            "inventory_imbalance_ratio": None,
            "quote_quality_label": base.get("quote_quality_label"),
            "effective_threshold": effective_threshold,
        },
        state=_paired_sequence_label(base),
        strategy_name=runtime.strategy_name,
        health_data=_health_snapshot(health_state),
    )
    live_eligible = (
        bool(base.get("qualifies"))
        and playbook_enabled(runtime.config, playbook_key, live=True)
        and bool(health_state.get("execution_allowed"))
        and runtime.live_requested
    )
    sequence_snapshot = _sequence_snapshot(sequence)
    return {
        **base,
        "playbook_key": playbook_key,
        "side": None,
        "local_date": context.local_date,
        "candidate_score": candidate_score,
        "live_eligible": live_eligible,
        "signal_data": sequence_snapshot["latest_signal_data"],
        "sequence_data": sequence_snapshot,
        "quote_snapshot": sequence_snapshot["latest_quote_snapshot"],
        "health_data": sequence_snapshot["latest_health_data"],
    }


def _evaluate_directional_playbook(
    *,
    context: WeatherMarketContext,
    market: WeatherBucketMarket,
    playbook_key: str,
    playbook: dict[str, Any],
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
    extremes: dict[str, Any],
    directional_ranges: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not bool(playbook.get("enabled", True)):
        return rows
    for side in playbook.get("target_sides") or ["yes", "no"]:
        directional_price = safe_float(market.yes_ask if side == "yes" else market.no_ask)
        complementary_price = safe_float(market.no_ask if side == "yes" else market.yes_ask)
        quote_age_seconds = _quote_age_seconds(market.latest_quote_time, captured_at)
        rejection_reasons: list[str] = []
        if directional_price is None:
            rejection_reasons.append("missing_directional_ask")
        if quote_age_seconds is None:
            rejection_reasons.append("missing_quote_time")
        else:
            max_quote_age = safe_float(playbook.get("max_quote_age_seconds") or 120.0)
            if max_quote_age is not None and quote_age_seconds > max_quote_age:
                rejection_reasons.append("stale_quote")
        if playbook_key == "tail_bucket_accumulation":
            if market.bucket_order not in {extremes.get("min_order"), extremes.get("max_order")}:
                rejection_reasons.append("not_tail_bucket")
            threshold = safe_float(playbook.get("directional_price_lte"))
            if directional_price is not None and threshold is not None and directional_price > threshold:
                rejection_reasons.append("directional_price_above_threshold")
        elif playbook_key == "cheap_bucket_accumulation":
            if market.bucket_order in {extremes.get("min_order"), extremes.get("max_order")}:
                rejection_reasons.append("tail_bucket_routed_to_tail_playbook")
            threshold = safe_float(playbook.get("directional_price_lte"))
            complementary_threshold = safe_float(playbook.get("complementary_price_gte"))
            if directional_price is not None and threshold is not None and directional_price > threshold:
                rejection_reasons.append("directional_price_above_threshold")
            if complementary_threshold is not None:
                if complementary_price is None:
                    rejection_reasons.append("missing_complementary_ask")
                elif complementary_price < complementary_threshold:
                    rejection_reasons.append("complementary_price_below_threshold")
        else:
            min_price = safe_float(playbook.get("directional_price_gte"))
            max_price = safe_float(playbook.get("directional_price_lte"))
            complementary_threshold = safe_float(playbook.get("complementary_price_lte"))
            if directional_price is not None and min_price is not None and directional_price < min_price:
                rejection_reasons.append("directional_price_below_threshold")
            if directional_price is not None and max_price is not None and directional_price > max_price:
                rejection_reasons.append("directional_price_above_threshold")
            best_for_side = safe_float((directional_ranges.get(side) or {}).get("max_price"))
            if (
                bool(playbook.get("require_dominant_bucket", False))
                and directional_price is not None
                and best_for_side is not None
                and directional_price + 1e-9 < best_for_side
            ):
                rejection_reasons.append("not_dominant_bucket")
            if complementary_threshold is not None:
                if complementary_price is None:
                    rejection_reasons.append("missing_complementary_ask")
                elif complementary_price > complementary_threshold:
                    rejection_reasons.append("complementary_price_above_threshold")
        qualifies = not rejection_reasons
        candidate_score = _directional_score(
            playbook_key=playbook_key,
            directional_price=directional_price,
            complementary_price=complementary_price,
        )
        sequence_key = f"{playbook_key}:{market.market_id}:{side}"
        sequence = _update_sequence_state(
            sequence_state=sequence_state,
            sequence_key=sequence_key,
            playbook_key=playbook_key,
            market=market,
            context=context,
            side=side,
            captured_at=captured_at,
            rolling_window_seconds=float(playbook.get("rolling_window_seconds") or 60.0),
            qualifies=qualifies,
            candidate_score=candidate_score,
            rejection_reasons=rejection_reasons,
            quote_snapshot=_quote_snapshot(market, captured_at=captured_at),
            signal_data={
                "directional_price": directional_price,
                "complementary_price": complementary_price,
                "quote_age_seconds": quote_age_seconds,
                "bucket_order": market.bucket_order,
                "min_bucket_order": extremes.get("min_order"),
                "max_bucket_order": extremes.get("max_order"),
            },
            state="directional" if qualifies else ("watching" if directional_price is not None else "idle"),
            strategy_name=runtime.strategy_name,
            health_data=_health_snapshot(health_state),
        )
        sequence_snapshot = _sequence_snapshot(sequence)
        rows.append(
            {
                "event_id": context.event_id,
                "event_slug": context.event_slug,
                "city": context.city,
                "local_date": context.local_date,
                "market_id": market.market_id,
                "market_slug": market.market_slug,
                "bucket_label": market.bucket_label,
                "question": market.question,
                "yes_token_id": market.yes_token_id,
                "no_token_id": market.no_token_id,
                "neg_risk": bool(market.neg_risk),
                "playbook_key": playbook_key,
                "side": side,
                "directional_price": directional_price,
                "complementary_price": complementary_price,
                "available_size": safe_float(market.yes_ask_size if side == "yes" else market.no_ask_size),
                "quote_age_seconds": quote_age_seconds,
                "qualifies": qualifies,
                "live_eligible": (
                    qualifies
                    and playbook_enabled(runtime.config, playbook_key, live=True)
                    and bool(health_state.get("execution_allowed"))
                    and runtime.live_requested
                ),
                "candidate_score": candidate_score,
                "rejection_reasons": rejection_reasons,
                "signal_data": sequence_snapshot["latest_signal_data"],
                "sequence_data": sequence_snapshot,
                "quote_snapshot": sequence_snapshot["latest_quote_snapshot"],
                "health_data": sequence_snapshot["latest_health_data"],
            }
        )
    return rows


def _evaluate_neg_risk_basket_playbook(
    *,
    context: WeatherMarketContext,
    playbook: dict[str, Any],
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not bool(playbook.get("enabled", True)):
        return []
    markets = [market for market in context.markets if bool(market.active) and bool(market.eligible)]
    if not markets:
        return []
    rows: list[dict[str, Any]] = []
    max_quote_age_seconds = safe_float(playbook.get("max_quote_age_seconds") or 120.0)
    min_distinct_conditions = max(1, int(playbook.get("min_distinct_conditions") or 3))
    synthetic_basket_cost_lte = safe_float(playbook.get("synthetic_basket_cost_lte") or 0.99) or 0.99
    max_unmatched_ratio = safe_float(playbook.get("max_unmatched_ratio") or 0.317073)
    require_sibling_coverage = bool(playbook.get("require_sibling_coverage", True))
    target_sides = [str(side).lower() for side in (playbook.get("target_sides") or ["yes"]) if str(side).lower() in {"yes", "no"}]
    if not target_sides:
        target_sides = ["yes"]
    for side in target_sides:
        available_legs: list[dict[str, Any]] = []
        rejection_reasons: list[str] = []
        missing_quote_count = 0
        stale_quote_count = 0
        for market in sorted(markets, key=lambda item: (item.bucket_order, str(item.bucket_label or ""))):
            quotes = complete_neg_risk_quotes(
                neg_risk=bool(market.neg_risk),
                yes_bid=safe_float(market.yes_bid),
                yes_ask=safe_float(market.yes_ask),
                yes_mid=safe_float(market.yes_mid),
                yes_bid_size=safe_float(market.yes_bid_size),
                yes_ask_size=safe_float(market.yes_ask_size),
                no_bid=safe_float(market.no_bid),
                no_ask=safe_float(market.no_ask),
                no_mid=safe_float(market.no_mid),
                no_bid_size=safe_float(market.no_bid_size),
                no_ask_size=safe_float(market.no_ask_size),
            )
            ask = safe_float(quotes.get(f"{side}_ask"))
            ask_size = safe_float(quotes.get(f"{side}_ask_size"))
            bid = safe_float(quotes.get(f"{side}_bid"))
            quote_age_seconds = _quote_age_seconds(market.latest_quote_time, captured_at)
            if ask is None or ask <= 0:
                missing_quote_count += 1
                continue
            if quote_age_seconds is None or (max_quote_age_seconds is not None and quote_age_seconds > max_quote_age_seconds):
                stale_quote_count += 1
                continue
            available_legs.append(
                {
                    "market_id": str(market.market_id or ""),
                    "market_slug": str(market.market_slug or ""),
                    "bucket_label": str(market.bucket_label or ""),
                    "bucket_order": int(market.bucket_order),
                    "token_id": str(market.yes_token_id if side == "yes" else market.no_token_id or ""),
                    "price": float(ask),
                    "bid": bid,
                    "ask_size": ask_size,
                    "quote_age_seconds": quote_age_seconds,
                }
            )
        if missing_quote_count > 0:
            rejection_reasons.append("missing_sibling_quote")
        if stale_quote_count > 0:
            rejection_reasons.append("stale_quote")
        if require_sibling_coverage and len(available_legs) < len(markets):
            rejection_reasons.append("missing_sibling_quote_coverage")
        if len(available_legs) < min_distinct_conditions:
            rejection_reasons.append("insufficient_sibling_conditions")

        selected_legs: list[dict[str, Any]] = []
        combined_cost = 0.0
        if available_legs:
            ordered_legs = sorted(
                available_legs,
                key=lambda item: (-float(item.get("price") or 0.0), int(item.get("bucket_order") or 0)),
            )
            for idx, leg in enumerate(ordered_legs):
                remaining = len(ordered_legs) - idx - 1
                must_take = len(selected_legs) + remaining < min_distinct_conditions
                next_cost = combined_cost + float(leg.get("price") or 0.0)
                if next_cost <= synthetic_basket_cost_lte + 1e-9 or must_take:
                    selected_legs.append(dict(leg))
                    combined_cost = next_cost
        if len(selected_legs) < min_distinct_conditions and "insufficient_sibling_conditions" not in rejection_reasons:
            rejection_reasons.append("insufficient_sibling_conditions")
        if combined_cost > synthetic_basket_cost_lte + 1e-9:
            rejection_reasons.append("synthetic_basket_cost_above_threshold")
        unmatched_ratio = max(0.0, 1.0 - combined_cost) if side == "yes" else 0.0
        if max_unmatched_ratio is not None and unmatched_ratio > max_unmatched_ratio + 1e-9:
            rejection_reasons.append("unmatched_ratio_above_threshold")
        qualifies = not rejection_reasons and bool(selected_legs)
        min_available_size = min(
            [float(leg.get("ask_size")) for leg in selected_legs if safe_float(leg.get("ask_size")) is not None],
            default=None,
        )
        candidate_score = round(
            max(0.0, synthetic_basket_cost_lte - combined_cost)
            * max(1.0, float(len(selected_legs)))
            * max(1.0, float(min_available_size or 1.0)),
            6,
        )
        synthetic_market_id = f"{context.event_id}:neg-risk-basket:{side}"
        quote_snapshot = {
            "captured_at": captured_at.isoformat(),
            "side": side,
            "combined_cost": round(combined_cost, 6),
            "selected_legs": [
                {
                    "market_id": leg["market_id"],
                    "bucket_label": leg["bucket_label"],
                    "price": round(float(leg["price"]), 6),
                    "bid": round(float(leg["bid"]), 6) if safe_float(leg.get("bid")) is not None else None,
                    "ask_size": round(float(leg["ask_size"]), 6) if safe_float(leg.get("ask_size")) is not None else None,
                }
                for leg in selected_legs
            ],
            "available_condition_count": len(available_legs),
            "total_condition_count": len(markets),
        }
        sequence = _update_event_sequence_state(
            sequence_state=sequence_state,
            sequence_key=f"neg_risk_basket:{context.event_id}:{side}",
            playbook_key="neg_risk_basket",
            event_id=context.event_id,
            event_slug=context.event_slug,
            city=context.city,
            local_date=context.local_date,
            market_id=synthetic_market_id,
            bucket_label="neg-risk-basket",
            side=side,
            captured_at=captured_at,
            rolling_window_seconds=float(playbook.get("rolling_window_seconds") or 60.0),
            qualifies=qualifies,
            candidate_score=candidate_score,
            rejection_reasons=rejection_reasons,
            quote_snapshot=quote_snapshot,
            signal_data={
                "side": side,
                "selected_legs": selected_legs,
                "combined_cost": round(combined_cost, 6),
                "selected_condition_count": len(selected_legs),
                "available_condition_count": len(available_legs),
                "total_condition_count": len(markets),
                "unmatched_ratio": round(unmatched_ratio, 6),
                "synthetic_basket_cost_lte": synthetic_basket_cost_lte,
                "max_unmatched_ratio": max_unmatched_ratio,
            },
            state="basketed" if qualifies else ("watching" if available_legs else "idle"),
            strategy_name=runtime.strategy_name,
            health_data=_health_snapshot(health_state),
        )
        sequence_snapshot = _sequence_snapshot(sequence)
        rows.append(
            {
                "event_id": context.event_id,
                "event_slug": context.event_slug,
                "city": context.city,
                "local_date": context.local_date,
                "market_id": synthetic_market_id,
                "condition_id": synthetic_market_id,
                "market_slug": f"{context.event_slug}-neg-risk-basket-{side}",
                "bucket_label": "neg-risk-basket",
                "question": f"{context.title} neg-risk basket {side}",
                "yes_token_id": None,
                "no_token_id": None,
                "neg_risk": True,
                "playbook_key": "neg_risk_basket",
                "side": side,
                "combined_cost": round(combined_cost, 6),
                "selected_condition_count": len(selected_legs),
                "available_condition_count": len(available_legs),
                "unmatched_ratio": round(unmatched_ratio, 6),
                "quote_age_seconds": max(
                    [float(leg.get("quote_age_seconds") or 0.0) for leg in selected_legs],
                    default=None,
                ),
                "qualifies": qualifies,
                "live_eligible": (
                    qualifies
                    and playbook_enabled(runtime.config, "neg_risk_basket", live=True)
                    and bool(health_state.get("execution_allowed"))
                    and runtime.live_requested
                ),
                "candidate_score": candidate_score,
                "rejection_reasons": rejection_reasons,
                "signal_data": sequence_snapshot["latest_signal_data"],
                "sequence_data": sequence_snapshot,
                "quote_snapshot": sequence_snapshot["latest_quote_snapshot"],
                "health_data": sequence_snapshot["latest_health_data"],
            }
        )
    return rows


def _evaluate_inventory_closeout_playbook(
    *,
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
    active_positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    playbook = (runtime.config.get("playbooks") or {}).get("inventory_exit_and_closeout") or {}
    if not bool(playbook.get("enabled", True)):
        return []
    rows: list[dict[str, Any]] = []
    partial_repair_window_seconds = float(playbook.get("partial_repair_window_seconds") or 30.0)
    max_merge_delay_minutes = float(playbook.get("max_merge_delay_minutes") or 240.0)
    for position in active_positions:
        opened_at = position.get("opened_at") or position.get("entry_detected_at")
        if not isinstance(opened_at, datetime):
            continue
        opened_at_utc = opened_at.astimezone(UTC) if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
        age_seconds = max(0.0, (captured_at - opened_at_utc).total_seconds())
        age_minutes = age_seconds / 60.0
        status = str(position.get("status") or "")
        qualifies = False
        closeout_reason = "monitor"
        rejection_reasons: list[str] = []
        if status == "partial_entry":
            qualifies = age_seconds >= partial_repair_window_seconds
            closeout_reason = "partial_repair_timeout"
            if not qualifies:
                rejection_reasons.append("partial_repair_window_open")
        elif status == "open_paired":
            qualifies = age_minutes >= max_merge_delay_minutes
            closeout_reason = "merge_delay_exceeded"
            if not qualifies:
                rejection_reasons.append("merge_delay_not_reached")
        else:
            rejection_reasons.append("position_status_not_actionable")
        candidate_score = round(age_minutes, 6)
        sequence_key = f"inventory_exit_and_closeout:{position.get('id')}"
        sequence = _update_position_sequence_state(
            sequence_state=sequence_state,
            sequence_key=sequence_key,
            playbook_key="inventory_exit_and_closeout",
            position=position,
            captured_at=captured_at,
            qualifies=qualifies,
            candidate_score=candidate_score,
            rejection_reasons=rejection_reasons,
            signal_data={
                "position_id": position.get("id"),
                "age_seconds": round(age_seconds, 6),
                "age_minutes": round(age_minutes, 6),
                "status": status,
                "closeout_reason": closeout_reason,
            },
            state="exiting" if qualifies else "watching",
            strategy_name=runtime.strategy_name,
            health_data=_health_snapshot(health_state),
        )
        sequence_snapshot = _sequence_snapshot(sequence)
        rows.append(
            {
                "event_id": str(position.get("event_id") or ""),
                "event_slug": str(position.get("event_slug") or ""),
                "city": str(position.get("city") or ""),
                "local_date": position.get("local_date"),
                "market_id": str(position.get("market_id") or ""),
                "bucket_label": str(position.get("bucket_label") or ""),
                "playbook_key": "inventory_exit_and_closeout",
                "side": position.get("side"),
                "qualifies": qualifies,
                "live_eligible": (
                    qualifies
                    and playbook_enabled(runtime.config, "inventory_exit_and_closeout", live=True)
                    and bool(health_state.get("execution_allowed"))
                    and runtime.live_requested
                ),
                "candidate_score": candidate_score,
                "rejection_reasons": rejection_reasons,
                "signal_data": sequence_snapshot["latest_signal_data"],
                "sequence_data": sequence_snapshot,
                "quote_snapshot": {},
                "health_data": sequence_snapshot["latest_health_data"],
            }
        )
    return rows


def _update_sequence_state(
    *,
    sequence_state: dict[str, dict[str, Any]],
    sequence_key: str,
    playbook_key: str,
    market: WeatherBucketMarket,
    context: WeatherMarketContext,
    side: str | None,
    captured_at: datetime,
    rolling_window_seconds: float,
    qualifies: bool,
    candidate_score: float,
    rejection_reasons: list[str],
    quote_snapshot: dict[str, Any],
    signal_data: dict[str, Any],
    state: str,
    strategy_name: str,
    health_data: dict[str, Any],
) -> dict[str, Any]:
    existing = sequence_state.get(sequence_key)
    if existing is not None:
        last_seen = existing["last_seen_at"]
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
        if (captured_at - last_seen).total_seconds() > rolling_window_seconds:
            existing = None
    if existing is None:
        existing = {
            "sequence_key": sequence_key,
            "strategy_name": strategy_name,
            "playbook_key": playbook_key,
            "market_id": market.market_id,
            "event_id": context.event_id,
            "event_slug": context.event_slug,
            "city": context.city,
            "local_date": context.local_date,
            "bucket_label": market.bucket_label,
            "side": side,
            "state": state,
            "first_seen_at": captured_at,
            "first_qualifying_at": captured_at if qualifies else None,
            "last_seen_at": captured_at,
            "last_qualifying_at": captured_at if qualifies else None,
            "detection_count": 0,
            "qualify_count": 0,
        }
    existing["state"] = state
    existing["last_seen_at"] = captured_at
    existing["detection_count"] = int(existing.get("detection_count") or 0) + 1
    if qualifies:
        existing["qualify_count"] = int(existing.get("qualify_count") or 0) + 1
        if existing.get("first_qualifying_at") is None:
            existing["first_qualifying_at"] = captured_at
        existing["last_qualifying_at"] = captured_at
    existing["latest_candidate_score"] = round(candidate_score, 6)
    existing["latest_rejection_reasons"] = list(rejection_reasons)
    existing["latest_quote_snapshot"] = quote_snapshot
    existing["latest_signal_data"] = signal_data
    existing["latest_health_data"] = health_data
    sequence_state[sequence_key] = existing
    return existing


def _update_position_sequence_state(
    *,
    sequence_state: dict[str, dict[str, Any]],
    sequence_key: str,
    playbook_key: str,
    position: dict[str, Any],
    captured_at: datetime,
    qualifies: bool,
    candidate_score: float,
    rejection_reasons: list[str],
    signal_data: dict[str, Any],
    state: str,
    strategy_name: str,
    health_data: dict[str, Any],
) -> dict[str, Any]:
    existing = sequence_state.get(sequence_key)
    if existing is None:
        existing = {
            "sequence_key": sequence_key,
            "strategy_name": strategy_name,
            "playbook_key": playbook_key,
            "market_id": str(position.get("market_id") or ""),
            "event_id": str(position.get("event_id") or ""),
            "event_slug": str(position.get("event_slug") or ""),
            "city": str(position.get("city") or ""),
            "local_date": position.get("local_date"),
            "bucket_label": str(position.get("bucket_label") or ""),
            "side": position.get("side"),
            "state": state,
            "first_seen_at": captured_at,
            "first_qualifying_at": captured_at if qualifies else None,
            "last_seen_at": captured_at,
            "last_qualifying_at": captured_at if qualifies else None,
            "detection_count": 0,
            "qualify_count": 0,
        }
    existing["state"] = state
    existing["last_seen_at"] = captured_at
    existing["detection_count"] = int(existing.get("detection_count") or 0) + 1
    if qualifies:
        existing["qualify_count"] = int(existing.get("qualify_count") or 0) + 1
        if existing.get("first_qualifying_at") is None:
            existing["first_qualifying_at"] = captured_at
        existing["last_qualifying_at"] = captured_at
    existing["latest_candidate_score"] = round(candidate_score, 6)
    existing["latest_rejection_reasons"] = list(rejection_reasons)
    existing["latest_quote_snapshot"] = {}
    existing["latest_signal_data"] = signal_data
    existing["latest_health_data"] = health_data
    sequence_state[sequence_key] = existing
    return existing


def _update_event_sequence_state(
    *,
    sequence_state: dict[str, dict[str, Any]],
    sequence_key: str,
    playbook_key: str,
    event_id: str,
    event_slug: str,
    city: str,
    local_date,
    market_id: str,
    bucket_label: str,
    side: str | None,
    captured_at: datetime,
    rolling_window_seconds: float,
    qualifies: bool,
    candidate_score: float,
    rejection_reasons: list[str],
    quote_snapshot: dict[str, Any],
    signal_data: dict[str, Any],
    state: str,
    strategy_name: str,
    health_data: dict[str, Any],
) -> dict[str, Any]:
    existing = sequence_state.get(sequence_key)
    if existing is not None:
        last_seen = existing["last_seen_at"]
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
        if (captured_at - last_seen).total_seconds() > rolling_window_seconds:
            existing = None
    if existing is None:
        existing = {
            "sequence_key": sequence_key,
            "strategy_name": strategy_name,
            "playbook_key": playbook_key,
            "market_id": market_id,
            "event_id": event_id,
            "event_slug": event_slug,
            "city": city,
            "local_date": local_date,
            "bucket_label": bucket_label,
            "side": side,
            "state": state,
            "first_seen_at": captured_at,
            "first_qualifying_at": captured_at if qualifies else None,
            "last_seen_at": captured_at,
            "last_qualifying_at": captured_at if qualifies else None,
            "detection_count": 0,
            "qualify_count": 0,
        }
    existing["state"] = state
    existing["last_seen_at"] = captured_at
    existing["detection_count"] = int(existing.get("detection_count") or 0) + 1
    if qualifies:
        existing["qualify_count"] = int(existing.get("qualify_count") or 0) + 1
        if existing.get("first_qualifying_at") is None:
            existing["first_qualifying_at"] = captured_at
        existing["last_qualifying_at"] = captured_at
    existing["latest_candidate_score"] = round(candidate_score, 6)
    existing["latest_rejection_reasons"] = list(rejection_reasons)
    existing["latest_quote_snapshot"] = quote_snapshot
    existing["latest_signal_data"] = signal_data
    existing["latest_health_data"] = health_data
    sequence_state[sequence_key] = existing
    return existing


def _paired_sequence_label(base: dict[str, Any]) -> str:
    if bool(base.get("qualifies")):
        return "paired"
    if safe_float(base.get("combined_cost")) is not None:
        return "watching"
    if base.get("quote_pair_available"):
        return "watching"
    return "idle"


def _health_snapshot(health_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_auth_status": (health_state.get("execution_auth") or {}).get("status"),
        "execution_auth_reason": (health_state.get("execution_auth") or {}).get("reason"),
        "market_data_status": (health_state.get("market_data") or {}).get("status"),
        "market_data_reason": (health_state.get("market_data") or {}).get("reason"),
        "quote_coverage_ratio": round(float(health_state.get("quote_coverage_ratio") or 0.0), 6),
    }


def _sequence_snapshot(sequence: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for key, value in sequence.items():
        if isinstance(value, dict):
            snapshot[key] = dict(value)
        elif isinstance(value, list):
            snapshot[key] = list(value)
        else:
            snapshot[key] = value
    return snapshot


def _quote_snapshot(market: WeatherBucketMarket, *, captured_at: datetime) -> dict[str, Any]:
    return {
        "captured_at": captured_at.isoformat(),
        "latest_quote_time": market.latest_quote_time.isoformat() if market.latest_quote_time else None,
        "yes_bid": market.yes_bid,
        "yes_ask": market.yes_ask,
        "yes_mid": market.yes_mid,
        "yes_bid_size": market.yes_bid_size,
        "yes_ask_size": market.yes_ask_size,
        "no_bid": market.no_bid,
        "no_ask": market.no_ask,
        "no_mid": market.no_mid,
        "no_bid_size": market.no_bid_size,
        "no_ask_size": market.no_ask_size,
    }


def _quote_age_seconds(latest_quote_time: datetime | None, captured_at: datetime) -> float | None:
    if latest_quote_time is None:
        return None
    quote_time = latest_quote_time.astimezone(UTC) if latest_quote_time.tzinfo else latest_quote_time.replace(tzinfo=UTC)
    return round((captured_at - quote_time).total_seconds(), 6)


def _quote_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    return round(max(0.0, float(best_ask) - float(best_bid)), 6)


def _bucket_extremes(context: WeatherMarketContext) -> dict[str, Any]:
    orders = [market.bucket_order for market in context.markets]
    if not orders:
        return {"min_order": None, "max_order": None}
    return {"min_order": min(orders), "max_order": max(orders)}


def _directional_side_ranges(context: WeatherMarketContext) -> dict[str, Any]:
    yes_prices = [safe_float(market.yes_ask) for market in context.markets]
    no_prices = [safe_float(market.no_ask) for market in context.markets]
    return {
        "yes": {"max_price": max([price for price in yes_prices if price is not None], default=None)},
        "no": {"max_price": max([price for price in no_prices if price is not None], default=None)},
    }


def _directional_score(
    *,
    playbook_key: str,
    directional_price: float | None,
    complementary_price: float | None = None,
) -> float:
    if directional_price is None:
        return 0.0
    if playbook_key == "tail_bucket_accumulation":
        return round(max(0.0, 0.10 - directional_price), 6)
    if playbook_key == "cheap_bucket_accumulation":
        return round(max(0.0, 0.08 - directional_price) + max(0.0, (complementary_price or 0.0) - 0.90), 6)
    if playbook_key == "high_prob_bucket_accumulation":
        return round(max(0.0, directional_price - 0.90) + max(0.0, 0.08 - (complementary_price or 1.0)), 6)
    return round(max(0.0, directional_price - 0.90), 6)


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
    playbook_rank = PLAYBOOK_ORDER.index(row["playbook_key"]) if row.get("playbook_key") in PLAYBOOK_ORDER else 999
    return (-playbook_rank, float(row.get("candidate_score") or 0.0), -(safe_float(row.get("combined_cost")) or 9.0))
