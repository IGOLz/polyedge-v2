"""Checkpoint state helpers for resumable wallet-forensics backfills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.wallet_forensics.utils import ensure_dir, utc_now

STATE_VERSION = 1


def backfill_scope_key(*, proxy_wallet: str, start_ts: int, end_ts: int | None) -> str:
    scope_end = "latest" if end_ts is None else str(end_ts)
    payload = f"{proxy_wallet.lower()}:{start_ts}:{scope_end}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def backfill_state_path(
    output_dir: Path,
    *,
    proxy_wallet: str,
    start_ts: int,
    end_ts: int | None,
) -> Path:
    scope_key = backfill_scope_key(proxy_wallet=proxy_wallet, start_ts=start_ts, end_ts=end_ts)
    return ensure_dir(output_dir) / f"backfill_state_{scope_key}.json"


def load_or_create_backfill_state(
    state_path: Path,
    *,
    target: dict[str, Any],
    start_ts: int,
    end_ts: int,
    open_ended: bool = False,
    reset: bool = False,
) -> dict[str, Any]:
    if not reset and state_path.exists():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if (
            loaded.get("version") == STATE_VERSION
            and str(loaded.get("proxy_wallet") or "").lower() == target["proxy_wallet"].lower()
            and loaded.get("scope", {}).get("start_ts") == start_ts
            and bool(loaded.get("scope", {}).get("open_ended")) == open_ended
            and (open_ended or loaded.get("scope", {}).get("end_ts") == end_ts)
        ):
            loaded.setdefault("scope", {})["end_ts"] = end_ts
            return loaded

    return {
        "version": STATE_VERSION,
        "proxy_wallet": target["proxy_wallet"],
        "profile_name": target.get("profile_name"),
        "created_at": utc_now().isoformat(),
        "updated_at": utc_now().isoformat(),
        "complete": False,
        "scope": {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "open_ended": open_ended,
        },
        "stages": {
            "value_snapshot": {"completed": False},
            "positions": {"completed": False},
            "closed_positions": {"completed": False},
            "activity": {"completed": False},
            "trades": {"completed": False},
            "market_context": {"completed": False},
            "receipts": {"completed": False},
        },
        "market_universe": [],
        "markets": {},
        "events": {},
        "receipts": {
            "completed_count": 0,
            "pending_count": 0,
            "last_transaction_hash": None,
        },
        "stats": {
            "activity_markets_completed": 0,
            "trade_markets_completed": 0,
            "event_context_completed": 0,
            "receipt_fetches_completed": 0,
        },
    }


def save_backfill_state(state_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now().isoformat()
    ensure_dir(state_path.parent)
    temp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(state_path)


def sync_market_universe(state: dict[str, Any], market_ids: list[str]) -> None:
    normalized = sorted({str(item).strip() for item in market_ids if str(item).strip()})
    state["market_universe"] = normalized
    for market_id in normalized:
        state["markets"].setdefault(
            market_id,
            {
                "activity_completed": False,
                "trade_completed": False,
                "activity_row_count": 0,
                "trade_row_count": 0,
                "event_slugs": [],
                "last_updated": None,
            },
        )


def mark_stage_completed(state: dict[str, Any], stage_name: str, **details: Any) -> None:
    stage = state["stages"].setdefault(stage_name, {})
    stage["completed"] = True
    stage["completed_at"] = utc_now().isoformat()
    for key, value in details.items():
        stage[key] = value


def mark_market_stage(
    state: dict[str, Any],
    market_id: str,
    *,
    stage_name: str,
    row_count: int,
    event_slugs: list[str],
) -> None:
    market_state = state["markets"].setdefault(
        market_id,
        {
            "activity_completed": False,
            "trade_completed": False,
            "activity_row_count": 0,
            "trade_row_count": 0,
            "event_slugs": [],
            "last_updated": None,
        },
    )
    if stage_name == "activity":
        market_state["activity_completed"] = True
        market_state["activity_row_count"] = row_count
    elif stage_name == "trade":
        market_state["trade_completed"] = True
        market_state["trade_row_count"] = row_count
    merged_event_slugs = sorted(set(market_state.get("event_slugs") or []).union(event_slugs))
    market_state["event_slugs"] = merged_event_slugs
    market_state["last_updated"] = utc_now().isoformat()
    state["stats"]["activity_markets_completed"] = sum(
        1 for item in state["markets"].values() if item.get("activity_completed")
    )
    state["stats"]["trade_markets_completed"] = sum(
        1 for item in state["markets"].values() if item.get("trade_completed")
    )


def market_stage_pending(state: dict[str, Any], market_id: str, *, stage_name: str) -> bool:
    market_state = state["markets"].get(market_id) or {}
    if stage_name == "activity":
        return not bool(market_state.get("activity_completed"))
    if stage_name == "trade":
        return not bool(market_state.get("trade_completed"))
    raise ValueError(f"Unsupported stage_name {stage_name!r}")


def pending_markets(state: dict[str, Any], *, stage_name: str) -> list[str]:
    return [
        market_id
        for market_id in state.get("market_universe") or []
        if market_stage_pending(state, market_id, stage_name=stage_name)
    ]


def mark_event_context_completed(
    state: dict[str, Any],
    event_slug: str,
    *,
    market_ids: list[str],
) -> None:
    event_state = state["events"].setdefault(event_slug, {})
    event_state["completed"] = True
    event_state["completed_at"] = utc_now().isoformat()
    event_state["market_ids"] = sorted({str(item).strip() for item in market_ids if str(item).strip()})
    state["stats"]["event_context_completed"] = sum(
        1 for item in state["events"].values() if item.get("completed")
    )


def event_context_pending(state: dict[str, Any], event_slug: str) -> bool:
    return not bool((state.get("events") or {}).get(event_slug, {}).get("completed"))


def update_receipt_progress(
    state: dict[str, Any],
    *,
    completed_count: int,
    pending_count: int,
    last_transaction_hash: str | None = None,
    completed: bool | None = None,
) -> None:
    state["receipts"]["completed_count"] = completed_count
    state["receipts"]["pending_count"] = pending_count
    state["receipts"]["last_transaction_hash"] = last_transaction_hash
    state["stats"]["receipt_fetches_completed"] = completed_count
    if completed is not None:
        stage = state["stages"].setdefault("receipts", {})
        stage["completed"] = completed
        if completed:
            stage["completed_at"] = utc_now().isoformat()


def finalize_backfill_state(state: dict[str, Any]) -> None:
    activity_done = not pending_markets(state, stage_name="activity")
    trades_done = not pending_markets(state, stage_name="trade")
    state["stages"]["activity"]["completed"] = activity_done
    if activity_done:
        state["stages"]["activity"]["completed_at"] = utc_now().isoformat()
    state["stages"]["trades"]["completed"] = trades_done
    if trades_done:
        state["stages"]["trades"]["completed_at"] = utc_now().isoformat()
    state["stages"]["market_context"]["completed"] = all(
        item.get("completed") for item in state.get("events", {}).values()
    ) if state.get("events") else True
    if state["stages"]["market_context"]["completed"]:
        state["stages"]["market_context"]["completed_at"] = utc_now().isoformat()

    state["complete"] = all(
        stage.get("completed")
        for stage in state.get("stages", {}).values()
    )


def summarize_backfill_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_path_present": True,
        "complete": bool(state.get("complete")),
        "market_total": len(state.get("market_universe") or []),
        "activity_markets_pending": len(pending_markets(state, stage_name="activity")),
        "trade_markets_pending": len(pending_markets(state, stage_name="trade")),
        "event_context_pending": sum(
            1 for item in (state.get("events") or {}).values() if not item.get("completed")
        ),
        "receipt_pending": int(state.get("receipts", {}).get("pending_count") or 0),
    }
