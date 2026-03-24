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
from trading_weather.clone_config import PLAYBOOK_ORDER, playbook_enabled
from weather.models import WeatherBucketMarket, WeatherMarketContext


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


def _normalize_pair_target_shares(yes_price: float, no_price: float, shares: int) -> int:
    if shares <= 0:
        return 0
    step = math.lcm(_buy_order_size_step(yes_price), _buy_order_size_step(no_price))
    return shares - (shares % step)


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
                    playbook=playbooks.get("paired_under_par") or {},
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
    combined_cost = safe_float(candidate.get("combined_cost"))
    yes_ask = safe_float(candidate.get("yes_ask"))
    no_ask = safe_float(candidate.get("no_ask"))
    yes_ask_size = safe_float(candidate.get("yes_ask_size"))
    no_ask_size = safe_float(candidate.get("no_ask_size"))
    if (
        candidate.get("playbook_key") != "paired_under_par"
        or combined_cost is None
        or yes_ask is None
        or no_ask is None
        or yes_ask_size is None
        or no_ask_size is None
        or combined_cost <= 0
    ):
        return None

    budget = max(
        0.0,
        min(
            float(runtime.runtime.get("sequence_budget_usd") or 0.0),
            float(runtime.runtime.get("max_total_exposure_usd") or 0.0) - active_exposure_usd,
        ),
    )
    if budget <= 0:
        return None
    target_shares = min(math.floor(budget / combined_cost), math.floor(min(yes_ask_size, no_ask_size)))
    target_shares = _normalize_pair_target_shares(yes_ask, no_ask, target_shares)
    min_target_shares = max(1, int(runtime.runtime.get("min_target_shares") or 1))
    if target_shares < min_target_shares:
        return None
    edge_per_share = 1.0 - combined_cost
    expected_edge_usd = round(edge_per_share * target_shares, 6)
    if expected_edge_usd < float(runtime.runtime.get("min_expected_edge_usd") or 0.0):
        return None
    first_side = "yes" if yes_ask_size <= no_ask_size else "no"
    second_side = "no" if first_side == "yes" else "yes"
    return {
        "playbook_key": "paired_under_par",
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
        "target_shares": target_shares,
        "expected_edge_usd": expected_edge_usd,
        "signal_score": safe_float(candidate.get("candidate_score")) or 0.0,
        "sequence_budget_usd": round(budget, 2),
        "first_side": first_side,
        "second_side": second_side,
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
    if playbook_key not in {"tail_bucket_accumulation", "high_prob_bucket_accumulation"}:
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
    if available_size is None or available_size <= 0:
        return None

    playbook = ((runtime.config.get("playbooks") or {}).get(playbook_key) or {})
    playbook_budget = float(playbook.get("sequence_budget_usd") or runtime.runtime.get("sequence_budget_usd") or 0.0)
    available_budget = max(0.0, float(runtime.runtime.get("max_total_exposure_usd") or 0.0) - active_exposure_usd)
    budget = max(0.0, min(playbook_budget, available_budget))
    if budget <= 0:
        return None

    target_shares = min(math.floor(budget / price), math.floor(available_size))
    target_shares = _normalize_buy_target_shares(price, target_shares)
    min_target_shares = max(1, int(runtime.runtime.get("min_target_shares") or 1))
    if target_shares < min_target_shares:
        return None

    profit_take_price = safe_float(playbook.get("profit_take_price"))
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
        f"contexts={int(summary.get('context_count') or 0)} "
        f"markets={int(summary.get('market_count') or 0)} "
        f"candidates={int(summary.get('candidate_count') or 0)} "
        f"sequences={int(summary.get('sequence_count') or 0)} "
        f"active_positions={int(summary.get('active_positions') or 0)} "
        f"entries={int(summary.get('entry_attempts') or 0)}"
    )
    top_candidate = summary.get("top_candidate") or {}
    if top_candidate:
        if top_candidate.get("playbook_key") == "paired_under_par":
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
    playbook: dict[str, Any],
    runtime: CloneRuntime,
    captured_at: datetime,
    health_state: dict[str, Any],
    sequence_state: dict[str, dict[str, Any]],
    active_market_ids: set[str],
) -> dict[str, Any]:
    playbook_key = "paired_under_par"
    live_rules = {
        "strategy_name": runtime.strategy_name,
        "complete_set_cost_lte": safe_float(playbook.get("synthetic_pair_cost_lte")) or 0.995,
        "max_inventory_imbalance_ratio": safe_float(playbook.get("max_inventory_imbalance_ratio")),
        "min_matched_size": safe_float(playbook.get("min_mergeable_size")) or 0.0,
        "max_quote_age_seconds": safe_float(playbook.get("max_quote_age_seconds")) or 120.0,
        "max_leg_spread": safe_float(playbook.get("max_leg_spread")) or 0.08,
        "require_full_quote_pair": bool(
            playbook.get("live_requires_full_quote_pair")
            if runtime.live_requested
            else playbook.get("shadow_requires_full_quote_pair")
        ),
        "midpoint_confirmation_required": bool(playbook.get("midpoint_confirmation_required", False)),
    }
    base = _evaluate_inventory_merge_candidate(
        context=context,
        market=market,
        live_rules=live_rules,
        captured_at=captured_at,
    )
    if str(base.get("market_id") or "") in active_market_ids:
        base["qualifies"] = False
        base["rejection_reasons"] = list(base.get("rejection_reasons") or []) + ["market_already_active"]

    combined_cost = safe_float(base.get("combined_cost"))
    merge_edge = safe_float(base.get("merge_edge")) or 0.0
    mergeable_size = safe_float(base.get("max_mergeable_size")) or 0.0
    candidate_score = round(max(0.0, merge_edge) * max(1.0, mergeable_size), 6)
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
            "inventory_imbalance_ratio": base.get("inventory_imbalance_ratio"),
            "quote_quality_label": base.get("quote_quality_label"),
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
        else:
            min_price = safe_float(playbook.get("directional_price_gte"))
            max_price = safe_float(playbook.get("directional_price_lte"))
            if directional_price is not None and min_price is not None and directional_price < min_price:
                rejection_reasons.append("directional_price_below_threshold")
            if directional_price is not None and max_price is not None and directional_price > max_price:
                rejection_reasons.append("directional_price_above_threshold")
            best_for_side = safe_float((directional_ranges.get(side) or {}).get("max_price"))
            if directional_price is not None and best_for_side is not None and directional_price + 1e-9 < best_for_side:
                rejection_reasons.append("not_dominant_bucket")
        qualifies = not rejection_reasons
        candidate_score = _directional_score(playbook_key=playbook_key, directional_price=directional_price)
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


def _directional_score(*, playbook_key: str, directional_price: float | None) -> float:
    if directional_price is None:
        return 0.0
    if playbook_key == "tail_bucket_accumulation":
        return round(max(0.0, 0.10 - directional_price), 6)
    return round(max(0.0, directional_price - 0.90), 6)


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
    playbook_rank = PLAYBOOK_ORDER.index(row["playbook_key"]) if row.get("playbook_key") in PLAYBOOK_ORDER else 999
    return (-playbook_rank, float(row.get("candidate_score") or 0.0), -(safe_float(row.get("combined_cost")) or 9.0))
