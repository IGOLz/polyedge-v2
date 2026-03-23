"""Database helpers for the dedicated weather merge bot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from shared.db import get_pool


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


async def create_weather_merge_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_merge_positions (
                id SERIAL PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                market_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                question TEXT,
                condition_id TEXT NOT NULL,
                neg_risk BOOLEAN NOT NULL DEFAULT FALSE,
                yes_token_id TEXT NOT NULL,
                no_token_id TEXT NOT NULL,
                status TEXT NOT NULL,
                first_side TEXT NOT NULL,
                target_shares NUMERIC(18,6) NOT NULL,
                paired_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                yes_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                no_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                yes_entry_price NUMERIC(12,6),
                no_entry_price NUMERIC(12,6),
                total_entry_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
                complete_set_cost NUMERIC(12,6),
                expected_edge_usdc NUMERIC(18,6),
                sequence_budget_usd NUMERIC(18,6),
                max_complete_set_cost NUMERIC(12,6),
                max_inventory_imbalance_ratio NUMERIC(12,6),
                yes_order_id TEXT,
                no_order_id TEXT,
                notes TEXT,
                signal_data JSONB,
                entry_detected_at TIMESTAMPTZ,
                opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_checked_at TIMESTAMPTZ,
                last_merged_at TIMESTAMPTZ,
                closed_at TIMESTAMPTZ,
                unwind_collateral_usdc NUMERIC(18,6) NOT NULL DEFAULT 0,
                merged_collateral_usdc NUMERIC(18,6) NOT NULL DEFAULT 0,
                redeemed_collateral_usdc NUMERIC(18,6) NOT NULL DEFAULT 0,
                merge_tx_hash TEXT,
                merge_tx_mode TEXT,
                merge_state TEXT,
                redeem_tx_hash TEXT,
                redeem_tx_mode TEXT,
                redeem_state TEXT
            )
            """
        )
        await conn.execute(
            """
            ALTER TABLE weather_merge_positions
            ADD COLUMN IF NOT EXISTS unwind_collateral_usdc NUMERIC(18,6) NOT NULL DEFAULT 0
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_merge_positions_active
            ON weather_merge_positions (status, market_id, opened_at DESC)
            """
        )


async def insert_weather_merge_position(
    *,
    plan: dict[str, Any],
    max_complete_set_cost: float,
    max_inventory_imbalance_ratio: float | None,
    status: str = "pending_entry",
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_merge_positions (
                strategy_name,
                market_id,
                event_id,
                event_slug,
                city,
                local_date,
                bucket_label,
                question,
                condition_id,
                neg_risk,
                yes_token_id,
                no_token_id,
                status,
                first_side,
                target_shares,
                paired_shares,
                yes_shares,
                no_shares,
                total_entry_cost,
                complete_set_cost,
                expected_edge_usdc,
                sequence_budget_usd,
                max_complete_set_cost,
                max_inventory_imbalance_ratio,
                signal_data,
                entry_detected_at
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26
            )
            RETURNING id
            """,
            plan["strategy_name"],
            plan["market_id"],
            plan["event_id"],
            plan["event_slug"],
            plan["city"],
            plan.get("local_date"),
            plan["bucket_label"],
            plan.get("question"),
            plan["condition_id"],
            bool(plan.get("neg_risk")),
            plan["yes_token_id"],
            plan["no_token_id"],
            status,
            plan["first_side"],
            Decimal(str(plan["target_shares"])),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal(str(plan["combined_cost"])),
            Decimal(str(plan["expected_edge_usd"])),
            Decimal(str(plan["sequence_budget_usd"])),
            Decimal(str(max_complete_set_cost)),
            Decimal(str(max_inventory_imbalance_ratio)) if max_inventory_imbalance_ratio is not None else None,
            json.dumps(plan.get("signal_data") or {}),
            datetime.now(timezone.utc),
        )
    return int(row["id"])


async def get_active_weather_merge_positions() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM weather_merge_positions
            WHERE closed_at IS NULL
            ORDER BY opened_at ASC
            """
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["signal_data"] = _maybe_json(item.get("signal_data"))
        result.append(item)
    return result


async def refresh_weather_position_balances(
    position_id: int,
    *,
    yes_shares: float,
    no_shares: float,
    paired_shares: float,
    status: str | None = None,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET yes_shares = $2,
                no_shares = $3,
                paired_shares = $4,
                status = COALESCE($5, status),
                notes = COALESCE($6, notes),
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(yes_shares, 6))),
            Decimal(str(round(no_shares, 6))),
            Decimal(str(round(paired_shares, 6))),
            status,
            notes,
        )


async def record_weather_entry_fill(
    position_id: int,
    *,
    side: str,
    shares: float,
    fill_price: float,
    order_id: str | None,
    total_entry_cost: float,
    status: str,
    notes: str | None = None,
) -> None:
    if side not in {"yes", "no"}:
        raise ValueError(f"Unexpected side: {side}")
    share_column = "yes_shares" if side == "yes" else "no_shares"
    price_column = "yes_entry_price" if side == "yes" else "no_entry_price"
    order_column = "yes_order_id" if side == "yes" else "no_order_id"
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            UPDATE weather_merge_positions
            SET {share_column} = {share_column} + $2,
                {price_column} = $3,
                {order_column} = COALESCE($4, {order_column}),
                total_entry_cost = $5,
                status = $6,
                notes = COALESCE($7, notes),
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(shares, 6))),
            Decimal(str(round(fill_price, 6))),
            order_id,
            Decimal(str(round(total_entry_cost, 6))),
            status,
            notes,
        )


async def record_weather_merge(
    position_id: int,
    *,
    merged_shares: float,
    merged_collateral_usdc: float,
    mode: str,
    transaction_hash: str,
    state: str | None,
    status: str,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET merged_collateral_usdc = merged_collateral_usdc + $2,
                merge_tx_mode = $3,
                merge_tx_hash = $4,
                merge_state = $5,
                status = $6,
                last_merged_at = NOW(),
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(merged_collateral_usdc, 6))),
            mode,
            transaction_hash,
            state,
            status,
        )


async def record_weather_redeem(
    position_id: int,
    *,
    redeemed_collateral_usdc: float,
    mode: str,
    transaction_hash: str,
    state: str | None,
    status: str,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET redeemed_collateral_usdc = redeemed_collateral_usdc + $2,
                redeem_tx_mode = $3,
                redeem_tx_hash = $4,
                redeem_state = $5,
                status = $6,
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(redeemed_collateral_usdc, 6))),
            mode,
            transaction_hash,
            state,
            status,
        )


async def record_weather_unwind(
    position_id: int,
    *,
    unwind_collateral_usdc: float,
    status: str,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET unwind_collateral_usdc = unwind_collateral_usdc + $2,
                status = $3,
                notes = COALESCE($4, notes),
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(unwind_collateral_usdc, 6))),
            status,
            notes,
        )


async def close_weather_merge_position(
    position_id: int,
    *,
    status: str,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET status = $2,
                notes = COALESCE($3, notes),
                last_checked_at = NOW(),
                closed_at = NOW()
            WHERE id = $1
            """,
            position_id,
            status,
            notes,
        )


async def update_weather_merge_status(
    position_id: int,
    *,
    status: str,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET status = $2,
                notes = COALESCE($3, notes),
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            status,
            notes,
        )


async def get_market_resolution(market_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT market_id, market_type, resolved, final_outcome, ended_at
            FROM market_outcomes
            WHERE market_id = $1
            """,
            market_id,
        )
    return dict(row) if row else None


async def get_daily_realized_pnl(day_start: datetime | None = None) -> float:
    if day_start is None:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(merged_collateral_usdc + redeemed_collateral_usdc + unwind_collateral_usdc - total_entry_cost), 0) AS pnl
            FROM weather_merge_positions
            WHERE closed_at >= $1
            """,
            day_start,
        )
    return float(row["pnl"] or 0.0) if row else 0.0
