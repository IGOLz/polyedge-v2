"""Heuristic strategy inference and shadow replay."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from analysis.wallet_forensics.constants import HIGH_CONFIDENCE_THRESHOLD
from analysis.wallet_forensics.utils import row_hash, safe_float


def infer_strategies(
    *,
    proxy_wallet: str,
    ledger_rows: list[dict[str, Any]],
    enriched_rows: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    ledger_by_condition = defaultdict(list)
    for row in enriched_rows:
        ledger_by_condition[str(row.get("condition_id") or "")].append(row)

    for condition_id, rows in ledger_by_condition.items():
        buys = [row for row in rows if row.get("event_type") == "trade" and row.get("side") == "buy"]
        yes_buys = [row for row in buys if row.get("outcome") == "Yes"]
        no_buys = [row for row in buys if row.get("outcome") == "No"]
        merges = [row for row in rows if row.get("event_type") == "merge"]
        context = market_context.get(condition_id, {})

        if yes_buys and no_buys and merges:
            rules.append(
                _rule(
                    proxy_wallet=proxy_wallet,
                    strategy_key="inventory_rebalancing_merge",
                    scope_type="condition",
                    scope_id=condition_id,
                    condition_id=condition_id,
                    asset=None,
                    confidence=0.92,
                    trade_ids=[item["ledger_event_id"] for item in yes_buys + no_buys],
                    summary="Bought both sides on the same condition and later merged inventory back into collateral.",
                    evidence={
                        "yes_buy_count": len(yes_buys),
                        "no_buy_count": len(no_buys),
                        "merge_count": len(merges),
                    },
                )
            )

        for row in buys:
            price = safe_float(row.get("price")) or 0.0
            if price <= 0.02:
                rules.append(
                    _rule(
                        proxy_wallet=proxy_wallet,
                        strategy_key="dust_long_tail_bucket",
                        scope_type="trade",
                        scope_id=row["ledger_event_id"],
                        condition_id=condition_id,
                        asset=row.get("asset"),
                        confidence=min(0.98, 0.80 + (0.02 - price) * 5),
                        trade_ids=[row["ledger_event_id"]],
                        summary="Bought a dust-priced tail bucket, consistent with convex payoff harvesting.",
                        evidence={"entry_price": price, "outcome": row.get("outcome")},
                    )
                )

            if row.get("is_weather") and row.get("weather_fair_yes_probability") is not None:
                fair_yes = safe_float(row.get("weather_fair_yes_probability")) or 0.0
                if row.get("outcome") == "Yes":
                    edge = fair_yes - price
                else:
                    edge = (1.0 - fair_yes) - price
                if edge >= 0.05:
                    rules.append(
                        _rule(
                            proxy_wallet=proxy_wallet,
                            strategy_key="weather_fair_value",
                            scope_type="trade",
                            scope_id=row["ledger_event_id"],
                            condition_id=condition_id,
                            asset=row.get("asset"),
                            confidence=min(0.97, 0.70 + edge * 2),
                            trade_ids=[row["ledger_event_id"]],
                            summary="Entry price was meaningfully below the ensemble-implied fair probability.",
                            evidence={
                                "entry_price": price,
                                "fair_yes_probability": fair_yes,
                                "edge": edge,
                                "forecast_age_seconds": row.get("weather_forecast_age_seconds"),
                            },
                        )
                    )

        if len(buys) >= 3:
            ladder_score = _price_ladder_score(buys)
            if ladder_score >= 0.66:
                rules.append(
                    _rule(
                        proxy_wallet=proxy_wallet,
                        strategy_key="laddered_execution",
                        scope_type="condition",
                        scope_id=condition_id,
                        condition_id=condition_id,
                        asset=None,
                        confidence=0.75,
                        trade_ids=[row["ledger_event_id"] for row in buys],
                        summary="Built the position through multiple staggered fills, consistent with laddered execution.",
                        evidence={"buy_count": len(buys), "ladder_score": ladder_score},
                    )
                )

        if context.get("neg_risk"):
            sibling_trades = _collect_event_buys(
                enriched_rows,
                event_slug=context.get("event_slug"),
            )
            if len(sibling_trades) >= 3:
                rules.append(
                    _rule(
                        proxy_wallet=proxy_wallet,
                        strategy_key="neg_risk_basket",
                        scope_type="event",
                        scope_id=context.get("event_slug") or condition_id,
                        condition_id=condition_id,
                        asset=None,
                        confidence=0.80,
                        trade_ids=[row["ledger_event_id"] for row in sibling_trades],
                        summary="Bought several related legs inside a negative-risk event, consistent with basket construction.",
                        evidence={
                            "event_slug": context.get("event_slug"),
                            "trade_count": len(sibling_trades),
                        },
                    )
                )

        redeems = [row for row in rows if row.get("event_type") == "redeem"]
        if redeems and context.get("end_date"):
            late = [
                row for row in redeems
                if row.get("occurred_at") and (row["occurred_at"] - context["end_date"]).total_seconds() >= 0
            ]
            if late:
                rules.append(
                    _rule(
                        proxy_wallet=proxy_wallet,
                        strategy_key="late_redemption_farming",
                        scope_type="condition",
                        scope_id=condition_id,
                        condition_id=condition_id,
                        asset=None,
                        confidence=0.78,
                        trade_ids=[row["ledger_event_id"] for row in late],
                        summary="Held winning inventory through resolution and redeemed directly for collateral.",
                        evidence={"redeem_count": len(late)},
                    )
                )

    deduped = {item["rule_id"]: item for item in rules}
    return list(deduped.values())


def build_shadow_replay(
    *,
    proxy_wallet: str,
    inferred_rules: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ledger_by_id = {row["ledger_event_id"]: row for row in ledger_rows}
    best_rule_by_trade: dict[str, dict[str, Any]] = {}
    for rule in inferred_rules:
        if rule["confidence"] < HIGH_CONFIDENCE_THRESHOLD:
            continue
        for trade_id in rule.get("trade_ids_json") or []:
            existing = best_rule_by_trade.get(trade_id)
            if existing is None or rule["confidence"] > existing["confidence"]:
                best_rule_by_trade[trade_id] = rule

    replay_rows: list[dict[str, Any]] = []
    for trade_id, rule in best_rule_by_trade.items():
        trade = ledger_by_id.get(trade_id)
        if not trade or trade.get("event_type") != "trade" or trade.get("side") != "buy":
            continue
        context = market_context.get(str(trade.get("condition_id") or ""), {})
        exit_price = _resolve_exit_mark(trade, context)
        if exit_price is None:
            continue
        entry_price = safe_float(trade.get("price")) or 0.0
        size = safe_float(trade.get("size")) or 0.0
        conservative_entry = min(0.99, entry_price + 0.01)
        payload = {
            "proxy_wallet": proxy_wallet,
            "rule_id": rule["rule_id"],
            "trade_id": trade_id,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size": size,
        }
        replay_rows.append(
            {
                "shadow_trade_id": row_hash(payload),
                "proxy_wallet": proxy_wallet,
                "rule_id": rule["rule_id"],
                "condition_id": trade.get("condition_id"),
                "asset": trade.get("asset"),
                "side": trade.get("side"),
                "entry_at": trade.get("occurred_at"),
                "entry_price": entry_price,
                "exit_mark_price": exit_price,
                "size": size,
                "resolved": bool(context.get("closed")),
                "pnl_slippage_free": size * (exit_price - entry_price),
                "pnl_conservative": size * (exit_price - conservative_entry),
                "payload_json": {
                    "source_trade": trade_id,
                    "strategy_key": rule["strategy_key"],
                },
            }
        )
    deduped = {row["shadow_trade_id"]: row for row in replay_rows}
    return list(deduped.values())


def _rule(
    *,
    proxy_wallet: str,
    strategy_key: str,
    scope_type: str,
    scope_id: str,
    condition_id: str | None,
    asset: str | None,
    confidence: float,
    summary: str,
    trade_ids: list[str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "proxy_wallet": proxy_wallet,
        "strategy_key": strategy_key,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "condition_id": condition_id,
        "asset": asset,
        "trade_ids": trade_ids,
        "summary": summary,
    }
    return {
        "rule_id": row_hash(payload),
        "proxy_wallet": proxy_wallet,
        "strategy_key": strategy_key,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "condition_id": condition_id,
        "asset": asset,
        "confidence": confidence,
        "summary": summary,
        "trade_ids_json": trade_ids,
        "evidence_json": evidence,
    }


def _price_ladder_score(rows: list[dict[str, Any]]) -> float:
    prices = [safe_float(row.get("price")) for row in rows]
    prices = [item for item in prices if item is not None]
    if len(prices) < 3:
        return 0.0
    ascending = sum(1 for left, right in zip(prices, prices[1:]) if right >= left)
    descending = sum(1 for left, right in zip(prices, prices[1:]) if right <= left)
    total = len(prices) - 1
    return max(ascending, descending) / total if total > 0 else 0.0


def _collect_event_buys(rows: list[dict[str, Any]], *, event_slug: str | None) -> list[dict[str, Any]]:
    if not event_slug:
        return []
    return [
        row for row in rows
        if row.get("event_slug") == event_slug and row.get("event_type") == "trade" and row.get("side") == "buy"
    ]


def _resolve_exit_mark(trade: dict[str, Any], context: dict[str, Any]) -> float | None:
    outcome = str(trade.get("outcome") or "")
    if outcome == "Yes":
        return safe_float(context.get("yes_price"))
    if outcome == "No":
        return safe_float(context.get("no_price"))
    return None
