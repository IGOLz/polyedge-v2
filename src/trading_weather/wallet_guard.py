"""Public-wallet guardrails for the dedicated weather merge bot."""

from __future__ import annotations

from typing import Any


WEATHER_TITLE_MARKERS = (
    "highest temperature",
    "lowest temperature",
)
WEATHER_SLUG_PREFIXES = (
    "highest-temperature-",
    "lowest-temperature-",
)


def classify_market_bucket(row: dict[str, Any]) -> str:
    title = str(row.get("title") or row.get("question") or "").strip().lower()
    slug = str(row.get("slug") or "").strip().lower()
    if any(marker in title for marker in WEATHER_TITLE_MARKERS):
        return "weather"
    if any(slug.startswith(prefix) for prefix in WEATHER_SLUG_PREFIXES):
        return "weather"
    if "-updown-" in slug:
        return "crypto_updown"
    return "other"


def public_market_id(row: dict[str, Any]) -> str | None:
    for key in ("conditionId", "market", "market_id"):
        value = row.get(key)
        if value:
            return str(value).strip()
    return None


def position_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bucket": classify_market_bucket(row),
        "market_id": public_market_id(row),
        "title": row.get("title") or row.get("question"),
        "slug": row.get("slug"),
        "outcome": row.get("outcome"),
        "size": row.get("size"),
        "avg_price": row.get("avgPrice"),
        "cur_price": row.get("curPrice"),
        "cash_pnl": row.get("cashPnl"),
        "redeemable": bool(row.get("redeemable")),
    }


def activity_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bucket": classify_market_bucket(row),
        "market_id": public_market_id(row),
        "timestamp": row.get("timestamp"),
        "type": row.get("type"),
        "title": row.get("title") or row.get("question"),
        "slug": row.get("slug"),
        "side": row.get("side"),
        "outcome": row.get("outcome"),
        "size": row.get("size"),
        "price": row.get("price"),
        "transaction_hash": row.get("transactionHash"),
    }


def audit_wallet_integrity(
    *,
    activity_rows: list[dict[str, Any]],
    position_rows: list[dict[str, Any]],
    tracked_weather_market_ids: set[str] | None,
    require_clean_wallet: bool,
    allow_orphaned_positions: bool,
) -> dict[str, Any]:
    tracked_ids = {str(item).strip() for item in (tracked_weather_market_ids or set()) if str(item).strip()}

    foreign_activity = [activity_brief(row) for row in activity_rows if classify_market_bucket(row) != "weather"]
    foreign_open_positions = [position_brief(row) for row in position_rows if classify_market_bucket(row) != "weather"]
    weather_open_positions = [position_brief(row) for row in position_rows if classify_market_bucket(row) == "weather"]
    orphaned_weather_positions = [
        row
        for row in weather_open_positions
        if not row.get("market_id") or str(row["market_id"]).strip() not in tracked_ids
    ]

    ready = True
    reason = None
    if require_clean_wallet and foreign_open_positions:
        ready = False
        reason = "foreign_open_positions_detected"
    elif require_clean_wallet and foreign_activity:
        ready = False
        reason = "foreign_wallet_activity_detected"
    elif not allow_orphaned_positions and orphaned_weather_positions:
        ready = False
        reason = "orphaned_weather_inventory_detected"

    return {
        "ready": ready,
        "reason": reason,
        "tracked_weather_market_ids": sorted(tracked_ids),
        "foreign_wallet_activity_detected": foreign_activity,
        "foreign_open_positions_detected": foreign_open_positions,
        "orphaned_weather_inventory_detected": orphaned_weather_positions,
        "weather_open_positions": weather_open_positions,
        "stats": {
            "foreign_activity_count": len(foreign_activity),
            "foreign_open_positions_count": len(foreign_open_positions),
            "weather_open_positions_count": len(weather_open_positions),
            "orphaned_weather_positions_count": len(orphaned_weather_positions),
            "tracked_weather_market_ids_count": len(tracked_ids),
        },
    }
