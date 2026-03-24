"""Database operations for the wallet tracker service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from shared.db import get_pool
from wallet_tracker.schema import DDL

logger = logging.getLogger(__name__)


async def create_wallet_tracker_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(DDL)
    logger.info("wallet_tracker tables ready")


async def get_watermark(profile_name: str) -> int | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT last_timestamp FROM wallet_tracker_watermark WHERE profile_name = $1",
        profile_name,
    )
    return int(row["last_timestamp"]) if row else None


async def update_watermark(profile_name: str, proxy_wallet: str, last_timestamp: int) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO wallet_tracker_watermark (profile_name, proxy_wallet, last_timestamp, updated_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (profile_name) DO UPDATE
            SET proxy_wallet = EXCLUDED.proxy_wallet,
                last_timestamp = EXCLUDED.last_timestamp,
                updated_at = EXCLUDED.updated_at
        """,
        profile_name,
        proxy_wallet,
        last_timestamp,
        datetime.now(UTC),
    )


async def insert_activity_rows(
    rows: list[dict[str, Any]],
    *,
    profile_name: str,
    proxy_wallet: str,
) -> int:
    if not rows:
        return 0

    pool = get_pool()
    inserted = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """
                INSERT INTO wallet_tracker_activity (
                    record_hash, profile_name, proxy_wallet, transaction_hash,
                    timestamp, event_type, condition_id, asset, side, outcome,
                    outcome_index, size, usdc_size, price,
                    event_slug, market_slug, title, payload_json, fetched_at
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14,
                    $15, $16, $17, $18::jsonb, $19
                )
                ON CONFLICT (record_hash) DO NOTHING
                """,
                row["record_hash"],
                profile_name,
                proxy_wallet,
                row.get("transactionHash") or row.get("transaction_hash"),
                int(row.get("timestamp") or 0),
                str(row.get("type") or row.get("event_type") or "").upper() or None,
                row.get("conditionId") or row.get("condition_id"),
                row.get("asset"),
                row.get("side"),
                row.get("outcome"),
                _safe_int(row.get("outcomeIndex") or row.get("outcome_index")),
                _safe_float(row.get("size")),
                _safe_float(row.get("usdcSize") or row.get("usdc_size")),
                _safe_float(row.get("price")),
                row.get("eventSlug") or row.get("event_slug"),
                row.get("marketSlug") or row.get("market_slug"),
                row.get("title"),
                json.dumps(row, default=str),
                datetime.now(UTC),
            )
            if result and "INSERT" in result:
                inserted += 1
    return inserted


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
