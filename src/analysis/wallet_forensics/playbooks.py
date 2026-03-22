"""Sequence-level playbook extraction and executable blueprint generation."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Any

from analysis.wallet_forensics.utils import row_hash, safe_float

CONDITION_SEQUENCE_GAP_SECONDS = 6 * 60 * 60
EVENT_SEQUENCE_GAP_SECONDS = 8 * 60 * 60
PRIMARY_STRATEGY_ORDER = (
    "inventory_rebalancing_merge",
    "neg_risk_basket",
    "late_redemption_farming",
    "weather_model_dislocation",
    "dust_long_tail_bucket",
    "laddered_execution",
)
BLUEPRINT_STATUS_RANK = {
    "ready_for_backtest": 3,
    "needs_exit_research": 2,
    "execution_overlay": 1,
    "operational_only": 0,
}
TERMINAL_SEQUENCE_EVENT_TYPES = {"merge", "redeem"}


def extract_playbook_sequences(
    *,
    proxy_wallet: str,
    ledger_rows: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    trade_strategies_by_id: dict[str, set[str]] = defaultdict(set)
    for rule in inferred_rules:
        strategy_key = str(rule.get("strategy_key") or "").strip()
        if not strategy_key:
            continue
        for trade_id in rule.get("trade_ids_json") or []:
            trade_key = str(trade_id or "").strip()
            if trade_key:
                trade_strategies_by_id[trade_key].add(strategy_key)

    sequences: list[dict[str, Any]] = []
    rows_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        condition_id = str(row.get("condition_id") or "").strip()
        if condition_id:
            rows_by_condition[condition_id].append(row)

    for condition_id, rows in rows_by_condition.items():
        for index, segment in enumerate(_segment_rows(rows, gap_seconds=CONDITION_SEQUENCE_GAP_SECONDS, split_on_terminal=True), start=1):
            sequence = _build_condition_sequence(
                proxy_wallet=proxy_wallet,
                condition_id=condition_id,
                sequence_index=index,
                rows=segment,
                trade_strategies_by_id=trade_strategies_by_id,
                market_context=market_context,
            )
            if sequence is not None:
                sequences.append(sequence)

    event_rows_by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        event_slug = str(row.get("event_slug") or "").strip()
        condition_id = str(row.get("condition_id") or "").strip()
        context = market_context.get(condition_id, {})
        if event_slug and context.get("neg_risk"):
            event_rows_by_slug[event_slug].append(row)

    for event_slug, rows in event_rows_by_slug.items():
        for index, segment in enumerate(_segment_rows(rows, gap_seconds=EVENT_SEQUENCE_GAP_SECONDS, split_on_terminal=False), start=1):
            sequence = _build_event_basket_sequence(
                proxy_wallet=proxy_wallet,
                event_slug=event_slug,
                sequence_index=index,
                rows=segment,
                market_context=market_context,
            )
            if sequence is not None:
                sequences.append(sequence)

    deduped = {row["sequence_id"]: row for row in sequences}
    return sorted(
        deduped.values(),
        key=lambda item: (
            item.get("started_at"),
            item.get("strategy_key") or "",
            item.get("condition_id") or item.get("event_slug") or "",
        ),
    )


def build_strategy_blueprints(
    *,
    proxy_wallet: str,
    playbook_sequences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sequences_by_strategy: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for sequence in playbook_sequences:
        primary_strategy = _normalize_strategy_key(sequence.get("strategy_key"))
        if primary_strategy:
            sequences_by_strategy[primary_strategy][sequence["sequence_id"]] = sequence
        tags = [_normalize_strategy_key(item) for item in sequence.get("strategy_tags_json") or []]
        for strategy_key in ("laddered_execution", "late_redemption_farming"):
            if strategy_key in tags:
                sequences_by_strategy[strategy_key][sequence["sequence_id"]] = sequence

    builders = {
        "inventory_rebalancing_merge": _build_inventory_merge_blueprint,
        "neg_risk_basket": _build_neg_risk_basket_blueprint,
        "weather_model_dislocation": _build_weather_dislocation_blueprint,
        "dust_long_tail_bucket": _build_dust_tail_blueprint,
        "laddered_execution": _build_laddered_execution_blueprint,
        "late_redemption_farming": _build_late_redemption_blueprint,
    }

    blueprints: list[dict[str, Any]] = []
    for strategy_key, rows_by_id in sequences_by_strategy.items():
        builder = builders.get(strategy_key, _build_generic_blueprint)
        blueprint = builder(
            proxy_wallet=proxy_wallet,
            strategy_key=strategy_key,
            sequences=list(rows_by_id.values()),
        )
        if blueprint is not None:
            blueprints.append(blueprint)

    blueprints.sort(
        key=lambda item: (
            BLUEPRINT_STATUS_RANK.get(str(item.get("status") or ""), -1),
            item.get("priority_score") or 0.0,
            item.get("support_count") or 0,
        ),
        reverse=True,
    )
    return blueprints


def _segment_rows(
    rows: list[dict[str, Any]],
    *,
    gap_seconds: int,
    split_on_terminal: bool,
) -> list[list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda item: (item.get("occurred_at"), item.get("ledger_event_id") or ""))
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in ordered:
        if not current:
            current = [row]
            continue
        previous = current[-1]
        gap = (row["occurred_at"] - previous["occurred_at"]).total_seconds()
        previous_terminal = str(previous.get("event_type") or "").lower() in TERMINAL_SEQUENCE_EVENT_TYPES
        if gap > gap_seconds or (split_on_terminal and previous_terminal):
            segments.append(current)
            current = [row]
            continue
        current.append(row)
    if current:
        segments.append(current)
    return segments


def _build_condition_sequence(
    *,
    proxy_wallet: str,
    condition_id: str,
    sequence_index: int,
    rows: list[dict[str, Any]],
    trade_strategies_by_id: dict[str, set[str]],
    market_context: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None

    ordered = sorted(rows, key=lambda item: (item.get("occurred_at"), item.get("ledger_event_id") or ""))
    trades = [row for row in ordered if row.get("event_type") == "trade"]
    buys = [row for row in trades if row.get("side") == "buy"]
    merges = [row for row in ordered if row.get("event_type") == "merge"]
    redeems = [row for row in ordered if row.get("event_type") == "redeem"]
    yes_buys = [row for row in buys if row.get("outcome") == "Yes"]
    no_buys = [row for row in buys if row.get("outcome") == "No"]
    context = market_context.get(condition_id, {})
    realized_pnl = sum(safe_float(row.get("realized_pnl")) or 0.0 for row in ordered)

    strategies: set[str] = set()
    for row in buys:
        for item in trade_strategies_by_id.get(str(row.get("ledger_event_id") or ""), set()):
            normalized = _normalize_strategy_key(item)
            if normalized:
                strategies.add(normalized)

    buy_usdc = sum(-(safe_float(row.get("usdc_delta")) or 0.0) for row in buys)
    yes_size = sum(safe_float(row.get("size")) or 0.0 for row in yes_buys)
    no_size = sum(safe_float(row.get("size")) or 0.0 for row in no_buys)
    matched_size = min(yes_size, no_size)
    total_side_size = yes_size + no_size
    imbalance_ratio = abs(yes_size - no_size) / total_side_size if total_side_size else None
    ladder_score = _price_ladder_score(buys)
    avg_weather_edge = _weather_trade_edge(buys, reducer="avg")
    max_weather_edge = _weather_trade_edge(buys, reducer="max")
    forecast_age_seconds = _median_numeric(row.get("weather_forecast_age_seconds") for row in buys)
    merge_delay_minutes = None
    if buys and (merges or redeems):
        terminal_time = (merges or redeems)[0].get("occurred_at")
        last_buy_time = buys[-1].get("occurred_at")
        if terminal_time is not None and last_buy_time is not None:
            merge_delay_minutes = (terminal_time - last_buy_time).total_seconds() / 60.0

    if yes_buys and no_buys and merges:
        strategies.add("inventory_rebalancing_merge")
    if _has_post_resolution_redeem(redeems, context):
        strategies.add("late_redemption_farming")
    if len(buys) >= 3 and ladder_score >= 0.66:
        strategies.add("laddered_execution")
    if (_min_trade_price(buys) or 1.0) <= 0.02:
        strategies.add("dust_long_tail_bucket")
    if avg_weather_edge is not None and avg_weather_edge >= 0.05:
        strategies.add("weather_model_dislocation")

    if not strategies:
        return None

    primary_strategy = _choose_primary_strategy(strategies)
    started_at = ordered[0]["occurred_at"]
    ended_at = ordered[-1]["occurred_at"]
    payload = {
        "buy_usdc": _rounded(buy_usdc),
        "min_entry_price": _rounded(_min_trade_price(buys)),
        "max_entry_price": _rounded(_max_trade_price(buys)),
        "avg_entry_price": _rounded(_avg_trade_price(buys)),
        "ladder_score": _rounded(ladder_score),
        "avg_weather_edge": _rounded(avg_weather_edge),
        "max_weather_edge": _rounded(max_weather_edge),
        "weather_forecast_age_seconds": _rounded(forecast_age_seconds),
        "matched_size": _rounded(matched_size),
        "complete_set_cost": _rounded(buy_usdc / matched_size) if matched_size else None,
        "inventory_imbalance_ratio": _rounded(imbalance_ratio),
        "merge_delay_minutes": _rounded(merge_delay_minutes),
        "buy_trade_ids": [str(row.get("ledger_event_id") or "") for row in buys if str(row.get("ledger_event_id") or "")],
        "terminal_event_type": _first_non_empty(item.get("event_type") for item in merges + redeems),
        "bucket_label": _first_non_empty(row.get("weather_bucket_label") for row in buys),
        "event_end_date": _event_end_date(context),
        "trade_notional": _rounded(sum(_trade_notional(row) for row in trades)),
    }
    summary = _sequence_summary(
        primary_strategy,
        trade_count=len(trades),
        condition_count=1,
        matched_size=matched_size,
        avg_weather_edge=avg_weather_edge,
        realized_pnl=realized_pnl,
    )
    sequence_id = row_hash(
        {
            "proxy_wallet": proxy_wallet,
            "scope_type": "condition",
            "condition_id": condition_id,
            "sequence_index": sequence_index,
            "strategy_key": primary_strategy,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }
    )
    return {
        "sequence_id": sequence_id,
        "proxy_wallet": proxy_wallet,
        "strategy_key": primary_strategy,
        "strategy_tags_json": sorted(strategies),
        "scope_type": "condition",
        "scope_id": condition_id,
        "condition_id": condition_id,
        "event_slug": _first_non_empty(row.get("event_slug") for row in ordered),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": (ended_at - started_at).total_seconds() / 60.0,
        "trade_count": len(trades),
        "buy_count": len(buys),
        "merge_count": len(merges),
        "redeem_count": len(redeems),
        "distinct_conditions": 1,
        "realized_pnl": realized_pnl,
        "confidence": _sequence_confidence(strategies, rows=ordered, payload=payload),
        "summary": summary,
        "payload_json": payload,
    }


def _build_event_basket_sequence(
    *,
    proxy_wallet: str,
    event_slug: str,
    sequence_index: int,
    rows: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None

    ordered = sorted(rows, key=lambda item: (item.get("occurred_at"), item.get("ledger_event_id") or ""))
    buys = [row for row in ordered if row.get("event_type") == "trade" and row.get("side") == "buy"]
    if not buys:
        return None

    condition_ids = sorted({str(row.get("condition_id") or "") for row in buys if str(row.get("condition_id") or "")})
    if len(condition_ids) < 3:
        return None

    same_side = _side_stats(buys)
    if same_side["dominant_count"] < 3:
        return None

    notional_by_condition: dict[str, float] = defaultdict(float)
    size_by_condition: dict[str, float] = defaultdict(float)
    for row in buys:
        condition_id = str(row.get("condition_id") or "")
        notional_by_condition[condition_id] += _trade_notional(row)
        size_by_condition[condition_id] += safe_float(row.get("size")) or 0.0
    matched_size = min(size_by_condition.values()) if size_by_condition else None
    total_cost = sum(notional_by_condition.values())
    complete_set_cost = total_cost / matched_size if matched_size else None
    payload = {
        "condition_count": len(condition_ids),
        "sample_condition_ids": condition_ids[:10],
        "dominant_side": same_side["dominant_side"],
        "dominant_side_count": same_side["dominant_count"],
        "matched_size": _rounded(matched_size),
        "complete_set_cost": _rounded(complete_set_cost),
        "unmatched_ratio": _rounded(same_side["unmatched_ratio"]),
        "trade_notional": _rounded(total_cost),
    }
    started_at = ordered[0]["occurred_at"]
    ended_at = ordered[-1]["occurred_at"]
    summary = _sequence_summary(
        "neg_risk_basket",
        trade_count=len(buys),
        condition_count=len(condition_ids),
        matched_size=matched_size,
        avg_weather_edge=None,
        realized_pnl=sum(safe_float(row.get("realized_pnl")) or 0.0 for row in ordered),
    )
    sequence_id = row_hash(
        {
            "proxy_wallet": proxy_wallet,
            "scope_type": "event",
            "event_slug": event_slug,
            "sequence_index": sequence_index,
            "strategy_key": "neg_risk_basket",
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }
    )
    return {
        "sequence_id": sequence_id,
        "proxy_wallet": proxy_wallet,
        "strategy_key": "neg_risk_basket",
        "strategy_tags_json": ["neg_risk_basket"],
        "scope_type": "event",
        "scope_id": event_slug,
        "condition_id": None,
        "event_slug": event_slug,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": (ended_at - started_at).total_seconds() / 60.0,
        "trade_count": len(buys),
        "buy_count": len(buys),
        "merge_count": sum(1 for row in ordered if row.get("event_type") == "merge"),
        "redeem_count": sum(1 for row in ordered if row.get("event_type") == "redeem"),
        "distinct_conditions": len(condition_ids),
        "realized_pnl": sum(safe_float(row.get("realized_pnl")) or 0.0 for row in ordered),
        "confidence": _sequence_confidence({"neg_risk_basket"}, rows=ordered, payload=payload),
        "summary": summary,
        "payload_json": payload,
    }


def _build_inventory_merge_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = _profitable_or_all(sequences)
    complete_set_cost = _median_numeric(
        sequence.get("payload_json", {}).get("complete_set_cost")
        for sequence in rows
    )
    imbalance_ratio = _median_numeric(
        sequence.get("payload_json", {}).get("inventory_imbalance_ratio")
        for sequence in rows
    )
    matched_size = _median_numeric(
        sequence.get("payload_json", {}).get("matched_size")
        for sequence in rows
    )
    merge_delay = _median_numeric(
        sequence.get("payload_json", {}).get("merge_delay_minutes")
        for sequence in rows
    )
    actionable_cost = min(0.995, complete_set_cost) if complete_set_cost is not None else 0.98
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="ready_for_backtest",
        sequences=sequences,
        summary=(
            "Accumulate both sides in the same condition when the reconstructed complete-set cost is below par, "
            "keep inventory roughly balanced, and exit by merging back into collateral."
        ),
        entry_rule={
            "condition": "same_condition_both_sides",
            "complete_set_cost_lte": _rounded(actionable_cost),
            "max_inventory_imbalance_ratio": _rounded(imbalance_ratio or 0.25),
        },
        sizing_rule={
            "matched_size_target": _rounded(matched_size or 5.0),
            "inventory_style": "match_smaller_side_and_rebalance",
        },
        exit_rule={
            "action": "merge",
            "when_inventory_matched": True,
            "expected_merge_delay_minutes": _rounded(merge_delay),
        },
        risk_rule={
            "avoid_unmatched_inventory": True,
            "max_complete_set_cost": 0.995,
            "force_flatten_before_resolution": True,
        },
        evidence={
            "median_complete_set_cost": _rounded(complete_set_cost),
            "actionable_complete_set_cost_lte": _rounded(actionable_cost),
            "median_inventory_imbalance_ratio": _rounded(imbalance_ratio),
            "median_matched_size": _rounded(matched_size),
            "median_merge_delay_minutes": _rounded(merge_delay),
        },
    )


def _build_neg_risk_basket_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = _profitable_or_all(sequences)
    complete_set_cost = _median_numeric(
        sequence.get("payload_json", {}).get("complete_set_cost")
        for sequence in rows
    )
    condition_count = _median_numeric(sequence.get("distinct_conditions") for sequence in rows)
    unmatched_ratio = _median_numeric(
        sequence.get("payload_json", {}).get("unmatched_ratio")
        for sequence in rows
    )
    status = "ready_for_backtest"
    actionable_cost = complete_set_cost
    if actionable_cost is None or actionable_cost > 1.05:
        status = "needs_exit_research"
        actionable_cost = 0.99
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status=status,
        sequences=sequences,
        summary=(
            "Construct a same-side basket across sibling negative-risk markets when the basket cost is below a "
            "synthetic complete set, then monetize through event completion or later operational exits."
        ),
        entry_rule={
            "condition": "neg_risk_event_basket",
            "min_distinct_conditions": max(3, int(round(condition_count or 3))),
            "complete_set_cost_lte": _rounded(actionable_cost or 0.99),
        },
        sizing_rule={
            "inventory_style": "equal_notional_per_condition",
            "max_unmatched_ratio": _rounded(unmatched_ratio or 0.20),
        },
        exit_rule={
            "action": "event_completion_or_conversion",
            "notes": "Needs explicit operational exit modeling beyond naive mark-to-market replay.",
        },
        risk_rule={
            "require_sibling_coverage": True,
            "max_basket_cost": 0.995,
            "limit_unmatched_tail_inventory": True,
        },
        evidence={
            "median_complete_set_cost": _rounded(complete_set_cost),
            "actionable_complete_set_cost_lte": _rounded(actionable_cost),
            "median_condition_count": _rounded(condition_count),
            "median_unmatched_ratio": _rounded(unmatched_ratio),
        },
    )


def _build_weather_dislocation_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = _profitable_or_all(sequences)
    edge = _median_numeric(sequence.get("payload_json", {}).get("avg_weather_edge") for sequence in rows)
    forecast_age = _median_numeric(
        sequence.get("payload_json", {}).get("weather_forecast_age_seconds") for sequence in rows
    )
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="needs_exit_research",
        sequences=sequences,
        summary=(
            "Enter weather buckets when ensemble-implied fair value is materially above the traded price, "
            "but do not treat entry alone as the full edge until the exit logic is reconstructed."
        ),
        entry_rule={
            "condition": "weather_model_edge",
            "min_model_edge": _rounded(edge or 0.05),
            "max_forecast_age_seconds": _rounded(forecast_age or 21600.0),
        },
        sizing_rule={
            "inventory_style": "edge_weighted",
            "max_single_bucket_concentration": 0.20,
        },
        exit_rule={
            "action": "research_required",
            "notes": "ColdMath's profitability is not explained by passive hold-to-mark replay.",
        },
        risk_rule={
            "require_live_forecast_refresh": True,
            "respect_resolution_cutoff_hours": 12,
        },
        evidence={
            "median_avg_weather_edge": _rounded(edge),
            "median_forecast_age_seconds": _rounded(forecast_age),
        },
    )


def _build_dust_tail_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = _profitable_or_all(sequences)
    min_entry_price = _median_numeric(
        sequence.get("payload_json", {}).get("min_entry_price") for sequence in rows
    )
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="needs_exit_research",
        sequences=sequences,
        summary=(
            "Pick up extremely low-priced tail buckets, likely as convex payoff scraps or as complements to a larger basket."
        ),
        entry_rule={
            "condition": "tail_bucket_pricing",
            "max_entry_price": _rounded(min_entry_price or 0.02),
        },
        sizing_rule={
            "inventory_style": "small_probe_or_basket_complement",
            "max_notional_per_bucket": 50.0,
        },
        exit_rule={
            "action": "research_required",
            "notes": "Standalone replay is weak; likely depends on basket context.",
        },
        risk_rule={
            "treat_as_add_on_only": True,
            "cap_total_tail_exposure": 0.10,
        },
        evidence={"median_min_entry_price": _rounded(min_entry_price)},
    )


def _build_laddered_execution_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ladder_score = _median_numeric(
        sequence.get("payload_json", {}).get("ladder_score") for sequence in sequences
    )
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="execution_overlay",
        sequences=sequences,
        summary=(
            "Scale into positions in multiple clips instead of crossing the full size immediately."
        ),
        entry_rule={"condition": "overlay_only"},
        sizing_rule={
            "inventory_style": "staggered_clips",
            "ladder_score_target": _rounded(ladder_score or 0.66),
        },
        exit_rule={"action": "inherits_primary_strategy_exit"},
        risk_rule={"max_clip_fraction": 0.40},
        evidence={"median_ladder_score": _rounded(ladder_score)},
    )


def _build_late_redemption_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="operational_only",
        sequences=sequences,
        summary=(
            "Hold winning inventory through resolution and redeem directly, treating redemption as an operational exit path rather than alpha by itself."
        ),
        entry_rule={"condition": "no_entry_signal"},
        sizing_rule={"inventory_style": "inherits_primary_strategy_position"},
        exit_rule={"action": "redeem_after_resolution"},
        risk_rule={"require_verified_resolution": True},
        evidence={"post_resolution_redeem_sequences": len(sequences)},
    )


def _build_generic_blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    sequences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return _blueprint(
        proxy_wallet=proxy_wallet,
        strategy_key=strategy_key,
        status="needs_exit_research",
        sequences=sequences,
        summary="Sequence cluster identified, but it still needs manual decomposition before it can be backtested as a standalone bot.",
        entry_rule={"condition": "manual_review_required"},
        sizing_rule={"inventory_style": "manual_review_required"},
        exit_rule={"action": "manual_review_required"},
        risk_rule={"notes": "Do not deploy before explicit rule extraction."},
        evidence={},
    )


def _blueprint(
    *,
    proxy_wallet: str,
    strategy_key: str,
    status: str,
    sequences: list[dict[str, Any]],
    summary: str,
    entry_rule: dict[str, Any],
    sizing_rule: dict[str, Any],
    exit_rule: dict[str, Any],
    risk_rule: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    support_count = len(sequences)
    realized_values = [safe_float(row.get("realized_pnl")) or 0.0 for row in sequences]
    distinct_conditions = len({str(row.get("condition_id") or "") for row in sequences if str(row.get("condition_id") or "")})
    distinct_events = len({str(row.get("event_slug") or "") for row in sequences if str(row.get("event_slug") or "")})
    win_rate = 0.0
    if realized_values:
        win_rate = sum(1 for value in realized_values if value > 0.0) / len(realized_values)
    payload = {
        "proxy_wallet": proxy_wallet,
        "strategy_key": strategy_key,
        "status": status,
        "support_count": support_count,
        "summary": summary,
    }
    return {
        "blueprint_id": row_hash(payload),
        "proxy_wallet": proxy_wallet,
        "strategy_key": strategy_key,
        "status": status,
        "confidence": _blueprint_confidence(sequences),
        "priority_score": _blueprint_priority_score(status=status, sequences=sequences),
        "support_count": support_count,
        "distinct_conditions": distinct_conditions,
        "distinct_events": distinct_events,
        "realized_pnl_total": sum(realized_values),
        "realized_pnl_avg": mean(realized_values) if realized_values else 0.0,
        "win_rate": win_rate,
        "summary": summary,
        "entry_rule_json": entry_rule,
        "sizing_rule_json": sizing_rule,
        "exit_rule_json": exit_rule,
        "risk_rule_json": risk_rule,
        "evidence_json": {
            **evidence,
            "sample_sequence_ids": [row["sequence_id"] for row in sequences[:10]],
        },
    }


def _sequence_summary(
    strategy_key: str,
    *,
    trade_count: int,
    condition_count: int,
    matched_size: float | None,
    avg_weather_edge: float | None,
    realized_pnl: float,
) -> str:
    if strategy_key == "inventory_rebalancing_merge":
        return (
            f"Built both sides across {trade_count} trades, matched about {_rounded(matched_size) or 0:.2f} contracts, "
            f"and exited through merge flow with realized PnL {_rounded(realized_pnl) or 0:.2f}."
        )
    if strategy_key == "neg_risk_basket":
        return (
            f"Built a same-side basket across {condition_count} sibling conditions with about {trade_count} trade fills."
        )
    if strategy_key == "weather_model_dislocation":
        return (
            f"Entered a weather bucket when estimated model edge was around {_rounded(avg_weather_edge) or 0:.3f}."
        )
    if strategy_key == "dust_long_tail_bucket":
        return f"Accumulated a low-priced tail bucket across {trade_count} trade fills."
    if strategy_key == "late_redemption_farming":
        return "Held inventory through resolution and redeemed after the event settled."
    if strategy_key == "laddered_execution":
        return f"Built the position through {trade_count} staggered trade fills."
    return f"Observed {strategy_key} across {trade_count} trades."


def _choose_primary_strategy(strategies: set[str]) -> str:
    for strategy_key in PRIMARY_STRATEGY_ORDER:
        if strategy_key in strategies:
            return strategy_key
    return sorted(strategies)[0]


def _normalize_strategy_key(value: Any) -> str:
    strategy_key = str(value or "").strip()
    if not strategy_key:
        return ""
    mapping = {
        "weather_fair_value": "weather_model_dislocation",
        "late_resolution_capture": "late_redemption_farming",
    }
    return mapping.get(strategy_key, strategy_key)


def _sequence_confidence(
    strategies: set[str],
    *,
    rows: list[dict[str, Any]],
    payload: dict[str, Any],
) -> float:
    base = 0.58
    if "inventory_rebalancing_merge" in strategies:
        base = max(base, 0.90)
    if "neg_risk_basket" in strategies:
        base = max(base, 0.82)
    if "weather_model_dislocation" in strategies:
        edge = safe_float(payload.get("avg_weather_edge")) or 0.0
        base = max(base, min(0.92, 0.70 + edge * 2.0))
    if "dust_long_tail_bucket" in strategies:
        price = safe_float(payload.get("min_entry_price")) or 0.0
        base = max(base, min(0.90, 0.76 + max(0.0, 0.02 - price) * 4.0))
    if "late_redemption_farming" in strategies:
        base = max(base, 0.78)
    if "laddered_execution" in strategies:
        base = max(base, 0.72)
    source_scores = [safe_float(row.get("source_confidence")) for row in rows]
    source_scores = [item for item in source_scores if item is not None]
    if source_scores:
        base = (base * 0.7) + (mean(source_scores) * 0.3)
    return max(0.0, min(0.99, base))


def _blueprint_confidence(sequences: list[dict[str, Any]]) -> float:
    values = [safe_float(sequence.get("confidence")) for sequence in sequences]
    values = [item for item in values if item is not None]
    if not values:
        return 0.0
    support_bonus = min(0.08, math.log10(len(values) + 1) * 0.05)
    return max(0.0, min(0.99, mean(values) + support_bonus))


def _blueprint_priority_score(*, status: str, sequences: list[dict[str, Any]]) -> float:
    status_weight = {
        "ready_for_backtest": 3.0,
        "needs_exit_research": 2.0,
        "execution_overlay": 1.0,
        "operational_only": 0.5,
    }.get(status, 0.0)
    support = len(sequences)
    realized_pnl = sum(safe_float(sequence.get("realized_pnl")) or 0.0 for sequence in sequences)
    confidence = _blueprint_confidence(sequences)
    return round(status_weight * 10 + support * 0.2 + max(0.0, realized_pnl) * 0.01 + confidence * 5, 4)


def _profitable_or_all(sequences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profitable = [row for row in sequences if (safe_float(row.get("realized_pnl")) or 0.0) > 0.0]
    return profitable or sequences


def _side_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("outcome") or "").strip()] += 1
    dominant_side = ""
    dominant_count = 0
    if counts:
        dominant_side, dominant_count = max(counts.items(), key=lambda item: item[1])
    total = sum(counts.values())
    unmatched_ratio = 0.0
    if total:
        unmatched_ratio = 1.0 - (dominant_count / total)
    return {
        "dominant_side": dominant_side,
        "dominant_count": dominant_count,
        "unmatched_ratio": unmatched_ratio,
    }


def _trade_notional(row: dict[str, Any]) -> float:
    usdc_delta = safe_float(row.get("usdc_delta"))
    if usdc_delta is not None:
        return abs(usdc_delta)
    size = safe_float(row.get("size")) or 0.0
    price = safe_float(row.get("price")) or 0.0
    return abs(size * price)


def _weather_trade_edge(rows: list[dict[str, Any]], *, reducer: str) -> float | None:
    values: list[float] = []
    for row in rows:
        fair_yes = safe_float(row.get("weather_fair_yes_probability"))
        price = safe_float(row.get("price"))
        outcome = str(row.get("outcome") or "")
        if fair_yes is None or price is None:
            continue
        if outcome == "Yes":
            values.append(fair_yes - price)
        elif outcome == "No":
            values.append((1.0 - fair_yes) - price)
    if not values:
        return None
    if reducer == "max":
        return max(values)
    return mean(values)


def _price_ladder_score(rows: list[dict[str, Any]]) -> float:
    prices = [safe_float(row.get("price")) for row in rows]
    prices = [item for item in prices if item is not None]
    if len(prices) < 3:
        return 0.0
    ascending = sum(1 for left, right in zip(prices, prices[1:]) if right >= left)
    descending = sum(1 for left, right in zip(prices, prices[1:]) if right <= left)
    total = len(prices) - 1
    return max(ascending, descending) / total if total else 0.0


def _has_post_resolution_redeem(redeems: list[dict[str, Any]], context: dict[str, Any]) -> bool:
    end_date = context.get("end_date")
    if end_date is None:
        return False
    for row in redeems:
        occurred_at = row.get("occurred_at")
        if occurred_at is not None and occurred_at >= end_date:
            return True
    return False


def _event_end_date(context: dict[str, Any]) -> str | None:
    end_date = context.get("end_date")
    if end_date is None:
        return None
    try:
        return end_date.isoformat()
    except AttributeError:
        return str(end_date)


def _payload_number(value: Any) -> float | None:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        value = stripped
    return safe_float(value)


def _first_non_empty(values) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _median_numeric(values) -> float | None:
    filtered = sorted(item for item in (_payload_number(value) for value in values) if item is not None)
    if not filtered:
        return None
    midpoint = len(filtered) // 2
    if len(filtered) % 2 == 1:
        return filtered[midpoint]
    return (filtered[midpoint - 1] + filtered[midpoint]) / 2.0


def _percentile(values, ratio: float) -> float | None:
    filtered = sorted(item for item in (_payload_number(value) for value in values) if item is not None)
    if not filtered:
        return None
    if len(filtered) == 1:
        return filtered[0]
    index = max(0, min(len(filtered) - 1, int(round((len(filtered) - 1) * ratio))))
    return filtered[index]


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _min_trade_price(rows: list[dict[str, Any]]) -> float | None:
    return _percentile((row.get("price") for row in rows), 0.0)


def _max_trade_price(rows: list[dict[str, Any]]) -> float | None:
    return _percentile((row.get("price") for row in rows), 1.0)


def _avg_trade_price(rows: list[dict[str, Any]]) -> float | None:
    prices = [safe_float(row.get("price")) for row in rows]
    prices = [item for item in prices if item is not None]
    if not prices:
        return None
    return mean(prices)
