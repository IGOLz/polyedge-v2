"""Ledger rebuild logic for public wallet activity."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from analysis.wallet_forensics.models import PositionState
from analysis.wallet_forensics.utils import parse_epoch_seconds, row_hash, safe_float


def build_wallet_ledger(
    *,
    proxy_wallet: str,
    activity_rows: list[dict[str, Any]],
    receipt_rows: dict[str, dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
    closed_positions_rows: list[dict[str, Any]],
    snapshot_mode: str = "history",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if snapshot_mode not in {"history", "final"}:
        raise ValueError(f"Unsupported snapshot_mode {snapshot_mode!r}")

    positions: dict[str, PositionState] = {}
    cumulative_realized = 0.0
    ledger_rows: list[dict[str, Any]] = []
    position_snapshots: list[dict[str, Any]] = []
    closed_outcome_map = _build_closed_outcome_map(closed_positions_rows)

    for row in sorted(activity_rows, key=_activity_sort_key):
        event_type = str(row.get("event_type") or row.get("type") or "").upper()
        if not event_type:
            continue
        condition_id = str(row.get("condition_id") or row.get("conditionId") or "")
        context = market_context.get(condition_id, {})
        receipt_summary = receipt_rows.get(str(row.get("transaction_hash") or row.get("transactionHash") or ""), {})
        event_time = parse_epoch_seconds(row.get("timestamp"))
        if event_time is None:
            continue

        realized_pnl = 0.0
        source_confidence = _source_confidence(event_type, receipt_summary)
        source_details = _build_source_details(
            event_type=event_type,
            row=row,
            receipt_summary=receipt_summary,
            source_confidence=source_confidence,
        )
        base_payload = {
            "raw_activity": row,
            "receipt_summary": receipt_summary,
        }

        if event_type == "TRADE":
            ledger_event, realized_pnl = _apply_trade(row, positions)
            if ledger_event is None:
                continue
            ledger_event["payload_json"] = base_payload
            ledger_event["source_details_json"] = source_details
            ledger_event["source_confidence"] = source_confidence
            ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, ledger_event, realized_pnl))

        elif event_type == "SPLIT":
            ledger_row_set, realized_pnl = _apply_split(row, positions, context)
            for item in ledger_row_set:
                item["payload_json"] = base_payload
                item["source_details_json"] = source_details
                item["source_confidence"] = source_confidence
                ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, item, 0.0))

        elif event_type == "MERGE":
            ledger_row_set, realized_pnl = _apply_merge(row, positions, context)
            for item in ledger_row_set:
                item["payload_json"] = base_payload
                item["source_details_json"] = source_details
                item["source_confidence"] = source_confidence
                row_realized = realized_pnl if item["event_type"] == "merge" else 0.0
                ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, item, row_realized))

        elif event_type == "REDEEM":
            ledger_event, realized_pnl = _apply_redeem(row, positions, context, closed_outcome_map)
            ledger_event["payload_json"] = base_payload
            ledger_event["source_details_json"] = source_details
            ledger_event["source_confidence"] = source_confidence
            ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, ledger_event, realized_pnl))

        elif event_type == "CONVERSION":
            ledger_row_set, realized_pnl = _apply_conversion(row, positions, context, market_context)
            for item in ledger_row_set:
                item["payload_json"] = base_payload
                item["source_details_json"] = source_details
                item["source_confidence"] = source_confidence
                ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, item, 0.0))

        elif event_type in {"REWARD", "MAKER_REBATE"}:
            usdc = safe_float(row.get("usdc_size") or row.get("usdcSize")) or 0.0
            realized_pnl = usdc
            ledger_row = {
                "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
                "condition_id": condition_id,
                "event_slug": row.get("event_slug") or row.get("eventSlug"),
                "asset": None,
                "outcome": None,
                "side": None,
                "event_type": event_type.lower(),
                "size": usdc,
                "token_delta": 0.0,
                "usdc_delta": usdc,
                "price": None,
                "payload_json": base_payload,
                "source_details_json": source_details,
                "source_confidence": source_confidence,
            }
            ledger_rows.append(_finalize_ledger_event(proxy_wallet, event_time, ledger_row, realized_pnl))

        else:
            continue

        cumulative_realized += realized_pnl
        if snapshot_mode == "history":
            position_snapshots.extend(
                _snapshot_positions(
                    proxy_wallet=proxy_wallet,
                    ledger_event_id=ledger_rows[-1]["ledger_event_id"],
                    positions=positions,
                    cumulative_realized=cumulative_realized,
                )
            )

    if snapshot_mode == "final" and ledger_rows:
        position_snapshots = _snapshot_positions(
            proxy_wallet=proxy_wallet,
            ledger_event_id=ledger_rows[-1]["ledger_event_id"],
            positions=positions,
            cumulative_realized=cumulative_realized,
        )

    return ledger_rows, position_snapshots


def _activity_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    return (
        int(row.get("timestamp") or 0),
        str(row.get("transaction_hash") or row.get("transactionHash") or ""),
        row_hash(row),
    )


def _apply_trade(row: dict[str, Any], positions: dict[str, PositionState]) -> tuple[dict[str, Any] | None, float]:
    asset = row.get("asset")
    if not asset:
        return None, 0.0
    condition_id = str(row.get("condition_id") or row.get("conditionId") or "")
    size = safe_float(row.get("size")) or 0.0
    price = safe_float(row.get("price"))
    usdc = safe_float(row.get("usdc_size") or row.get("usdcSize"))
    if usdc is None and price is not None:
        usdc = size * price
    usdc = usdc or 0.0
    side = str(row.get("side") or "").upper()
    outcome = row.get("outcome")

    state = positions.setdefault(
        asset,
        PositionState(asset=asset, condition_id=condition_id, outcome=outcome),
    )
    realized = 0.0
    token_delta = 0.0
    usdc_delta = 0.0

    if side == "BUY":
        state.size += size
        state.cost_basis += usdc
        token_delta = size
        usdc_delta = -usdc
    elif side == "SELL":
        sold = min(size, state.size)
        avg_cost = state.average_cost
        removed_cost = sold * avg_cost
        proceeds = sold * (price or 0.0)
        state.size -= sold
        state.cost_basis = max(0.0, state.cost_basis - removed_cost)
        realized = proceeds - removed_cost
        state.realized_pnl += realized
        token_delta = -sold
        usdc_delta = proceeds
    else:
        return None, 0.0

    return {
        "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
        "condition_id": condition_id,
        "event_slug": row.get("event_slug") or row.get("eventSlug"),
        "asset": asset,
        "outcome": outcome,
        "side": side.lower(),
        "event_type": "trade",
        "size": size,
        "token_delta": token_delta,
        "usdc_delta": usdc_delta,
        "price": price,
    }, realized


def _apply_split(row: dict[str, Any], positions: dict[str, PositionState], context: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    size = safe_float(row.get("size")) or 0.0
    usdc = safe_float(row.get("usdc_size") or row.get("usdcSize")) or size
    yes_asset = context.get("yes_token_id")
    no_asset = context.get("no_token_id")
    yes_cost = usdc / 2.0
    no_cost = usdc - yes_cost
    rows: list[dict[str, Any]] = []
    for asset, outcome, allocated_cost in (
        (yes_asset, "Yes", yes_cost),
        (no_asset, "No", no_cost),
    ):
        if not asset:
            continue
        state = positions.setdefault(
            asset,
            PositionState(asset=asset, condition_id=context.get("market_id") or row.get("condition_id"), outcome=outcome),
        )
        state.size += size
        state.cost_basis += allocated_cost
        rows.append(
            {
                "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
                "condition_id": row.get("condition_id") or row.get("conditionId"),
                "event_slug": row.get("event_slug") or row.get("eventSlug"),
                "asset": asset,
                "outcome": outcome,
                "side": "split",
                "event_type": "split",
                "size": size,
                "token_delta": size,
                "usdc_delta": -allocated_cost,
                "price": 0.5,
            }
        )
    return rows, 0.0


def _apply_merge(row: dict[str, Any], positions: dict[str, PositionState], context: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    size = safe_float(row.get("size")) or 0.0
    usdc = safe_float(row.get("usdc_size") or row.get("usdcSize")) or size
    yes_asset = context.get("yes_token_id")
    no_asset = context.get("no_token_id")
    yes_state = positions.get(yes_asset) if yes_asset else None
    no_state = positions.get(no_asset) if no_asset else None
    mergeable = min(
        size,
        yes_state.size if yes_state else 0.0,
        no_state.size if no_state else 0.0,
    )
    rows: list[dict[str, Any]] = []
    removed_total_cost = 0.0
    for asset, outcome, state in ((yes_asset, "Yes", yes_state), (no_asset, "No", no_state)):
        if not asset or state is None:
            continue
        removed_cost = mergeable * state.average_cost
        state.size = max(0.0, state.size - mergeable)
        state.cost_basis = max(0.0, state.cost_basis - removed_cost)
        removed_total_cost += removed_cost
        rows.append(
            {
                "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
                "condition_id": row.get("condition_id") or row.get("conditionId"),
                "event_slug": row.get("event_slug") or row.get("eventSlug"),
                "asset": asset,
                "outcome": outcome,
                "side": "merge",
                "event_type": "merge_burn_leg",
                "size": mergeable,
                "token_delta": -mergeable,
                "usdc_delta": 0.0,
                "price": None,
            }
        )

    realized = usdc - removed_total_cost
    rows.append(
        {
            "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
            "condition_id": row.get("condition_id") or row.get("conditionId"),
            "event_slug": row.get("event_slug") or row.get("eventSlug"),
            "asset": None,
            "outcome": None,
            "side": "merge",
            "event_type": "merge",
            "size": mergeable,
            "token_delta": 0.0,
            "usdc_delta": usdc,
            "price": None,
        }
    )
    return rows, realized


def _apply_redeem(
    row: dict[str, Any],
    positions: dict[str, PositionState],
    context: dict[str, Any],
    closed_outcome_map: dict[str, str],
) -> tuple[dict[str, Any], float]:
    condition_id = str(row.get("condition_id") or row.get("conditionId") or "")
    size = safe_float(row.get("size")) or 0.0
    usdc = safe_float(row.get("usdc_size") or row.get("usdcSize")) or size
    winning_outcome = closed_outcome_map.get(condition_id)
    yes_asset = context.get("yes_token_id")
    no_asset = context.get("no_token_id")
    if winning_outcome == "Yes":
        asset = yes_asset
        outcome = "Yes"
    elif winning_outcome == "No":
        asset = no_asset
        outcome = "No"
    else:
        asset, outcome = _pick_redeem_asset(size, yes_asset, no_asset, positions)
    state = positions.get(asset) if asset else None
    removed = min(size, state.size if state else 0.0)
    removed_cost = removed * (state.average_cost if state else 0.0)
    if state:
        state.size = max(0.0, state.size - removed)
        state.cost_basis = max(0.0, state.cost_basis - removed_cost)
        state.realized_pnl += usdc - removed_cost
    realized = usdc - removed_cost
    return {
        "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
        "condition_id": condition_id,
        "event_slug": row.get("event_slug") or row.get("eventSlug"),
        "asset": asset,
        "outcome": outcome,
        "side": "redeem",
        "event_type": "redeem",
        "size": removed,
        "token_delta": -removed,
        "usdc_delta": usdc,
        "price": 1.0,
    }, realized


def _apply_conversion(
    row: dict[str, Any],
    positions: dict[str, PositionState],
    context: dict[str, Any],
    market_context: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    condition_id = str(row.get("condition_id") or row.get("conditionId") or "")
    size = safe_float(row.get("size")) or 0.0
    no_asset = context.get("no_token_id")
    source_state = positions.get(no_asset) if no_asset else None
    source_size = min(size, source_state.size if source_state else 0.0)
    transferred_cost = source_size * (source_state.average_cost if source_state else 0.0)
    if source_state:
        source_state.size = max(0.0, source_state.size - source_size)
        source_state.cost_basis = max(0.0, source_state.cost_basis - transferred_cost)

    sibling_market_ids = [item for item in context.get("sibling_market_ids") or [] if item != condition_id]
    allocation = transferred_cost / max(len(sibling_market_ids), 1)
    rows: list[dict[str, Any]] = []
    if no_asset:
        rows.append(
            {
                "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
                "condition_id": condition_id,
                "event_slug": row.get("event_slug") or row.get("eventSlug"),
                "asset": no_asset,
                "outcome": "No",
                "side": "conversion",
                "event_type": "conversion_burn_leg",
                "size": source_size,
                "token_delta": -source_size,
                "usdc_delta": 0.0,
                "price": None,
            }
        )

    for sibling_id in sibling_market_ids:
        sibling = market_context.get(str(sibling_id), {})
        yes_asset = sibling.get("yes_token_id")
        if not yes_asset:
            continue
        state = positions.setdefault(
            yes_asset,
            PositionState(asset=yes_asset, condition_id=str(sibling_id), outcome="Yes"),
        )
        state.size += source_size
        state.cost_basis += allocation
        rows.append(
            {
                "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
                "condition_id": str(sibling_id),
                "event_slug": sibling.get("event_slug") or row.get("event_slug") or row.get("eventSlug"),
                "asset": yes_asset,
                "outcome": "Yes",
                "side": "conversion",
                "event_type": "conversion_mint_leg",
                "size": source_size,
                "token_delta": source_size,
                "usdc_delta": 0.0,
                "price": None,
            }
        )

    rows.append(
        {
            "transaction_hash": row.get("transaction_hash") or row.get("transactionHash"),
            "condition_id": condition_id,
            "event_slug": row.get("event_slug") or row.get("eventSlug"),
            "asset": None,
            "outcome": None,
            "side": "conversion",
            "event_type": "conversion",
            "size": source_size,
            "token_delta": 0.0,
            "usdc_delta": 0.0,
            "price": None,
        }
    )
    return rows, 0.0


def _pick_redeem_asset(size: float, yes_asset: str | None, no_asset: str | None, positions: dict[str, PositionState]) -> tuple[str | None, str | None]:
    yes_state = positions.get(yes_asset) if yes_asset else None
    no_state = positions.get(no_asset) if no_asset else None
    yes_size = yes_state.size if yes_state else 0.0
    no_size = no_state.size if no_state else 0.0
    if yes_size >= size and yes_size >= no_size:
        return yes_asset, "Yes"
    if no_size >= size:
        return no_asset, "No"
    if yes_size >= no_size:
        return yes_asset, "Yes"
    return no_asset, "No"


def _build_closed_outcome_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        condition_id = str(row.get("condition_id") or row.get("conditionId") or "")
        outcome = row.get("outcome")
        if condition_id and outcome in {"Yes", "No"}:
            result.setdefault(condition_id, outcome)
    return result


def _source_confidence(event_type: str, receipt_summary: dict[str, Any]) -> float:
    classifications = {str(item).lower() for item in receipt_summary.get("classifications") or []}
    wanted = event_type.lower()
    if wanted in classifications:
        return 0.95
    if classifications:
        return 0.75
    return 0.60


def _build_source_details(
    *,
    event_type: str,
    row: dict[str, Any],
    receipt_summary: dict[str, Any],
    source_confidence: float,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "activity_event_type": event_type.lower(),
        "source_confidence": source_confidence,
        "receipt_available": bool(receipt_summary),
    }
    tx_hash = str(row.get("transaction_hash") or row.get("transactionHash") or "").strip()
    if tx_hash:
        details["transaction_hash"] = tx_hash

    classifications = sorted(
        {
            str(item).lower()
            for item in receipt_summary.get("classifications") or []
            if str(item).strip()
        }
    )
    if classifications:
        details["receipt_classifications"] = classifications

    touched_contracts = sorted(
        {
            str(item).lower()
            for item in receipt_summary.get("touched_contracts") or []
            if str(item).strip()
        }
    )
    if touched_contracts:
        details["touched_contracts"] = touched_contracts

    for key in ("block_number", "block_timestamp", "usdc_in", "usdc_out"):
        value = receipt_summary.get(key)
        if value is not None:
            details[key] = value
    return details


def _finalize_ledger_event(proxy_wallet: str, event_time, row: dict[str, Any], realized_pnl: float) -> dict[str, Any]:
    payload = {
        "proxy_wallet": proxy_wallet,
        "occurred_at": event_time.isoformat(),
        "transaction_hash": row.get("transaction_hash"),
        "condition_id": row.get("condition_id"),
        "asset": row.get("asset"),
        "event_type": row.get("event_type"),
        "size": row.get("size"),
        "token_delta": row.get("token_delta"),
        "usdc_delta": row.get("usdc_delta"),
        "price": row.get("price"),
    }
    return {
        "ledger_event_id": row_hash(payload),
        "proxy_wallet": proxy_wallet,
        "occurred_at": event_time,
        "transaction_hash": row.get("transaction_hash"),
        "condition_id": row.get("condition_id"),
        "event_slug": row.get("event_slug"),
        "asset": row.get("asset"),
        "outcome": row.get("outcome"),
        "side": row.get("side"),
        "event_type": row.get("event_type"),
        "size": row.get("size"),
        "token_delta": row.get("token_delta"),
        "usdc_delta": row.get("usdc_delta"),
        "price": row.get("price"),
        "realized_pnl": realized_pnl,
        "source_confidence": row.get("source_confidence", 0.0),
        "source_details_json": row.get("source_details_json") or {},
        "payload_json": row.get("payload_json") or {},
    }


def _snapshot_positions(
    *,
    proxy_wallet: str,
    ledger_event_id: str,
    positions: dict[str, PositionState],
    cumulative_realized: float,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for state in positions.values():
        snapshot_payload = {
            "proxy_wallet": proxy_wallet,
            "ledger_event_id": ledger_event_id,
            "asset": state.asset,
            "size": state.size,
            "average_cost": state.average_cost,
            "cost_basis": state.cost_basis,
            "realized_pnl_cumulative": cumulative_realized,
        }
        snapshots.append(
            {
                "snapshot_id": row_hash(snapshot_payload),
                "proxy_wallet": proxy_wallet,
                "ledger_event_id": ledger_event_id,
                "condition_id": state.condition_id,
                "asset": state.asset,
                "outcome": state.outcome,
                "position_size": state.size,
                "average_cost": state.average_cost,
                "cost_basis": state.cost_basis,
                "realized_pnl_cumulative": cumulative_realized,
                "payload_json": asdict(state),
            }
        )
    return snapshots
