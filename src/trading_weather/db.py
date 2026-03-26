"""Database helpers for the dedicated weather merge bot."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
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


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


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
                bot_trade_id INTEGER,
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
            ALTER TABLE weather_merge_positions
            ADD COLUMN IF NOT EXISTS bot_trade_id INTEGER
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_merge_positions_active
            ON weather_merge_positions (status, market_id, opened_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_merge_position_events (
                id SERIAL PRIMARY KEY,
                position_id INTEGER NOT NULL REFERENCES weather_merge_positions(id) ON DELETE CASCADE,
                bot_trade_id INTEGER,
                event_type TEXT NOT NULL,
                event_status TEXT,
                side TEXT,
                order_id TEXT,
                tx_hash TEXT,
                tx_mode TEXT,
                tx_state TEXT,
                shares NUMERIC(18,6),
                price NUMERIC(12,6),
                value_usdc NUMERIC(18,6),
                notes TEXT,
                data JSONB,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_merge_position_events_position
            ON weather_merge_position_events (position_id, occurred_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_merge_cycles (
                id SERIAL PRIMARY KEY,
                captured_at TIMESTAMPTZ NOT NULL,
                strategy_name TEXT NOT NULL,
                dry_run BOOLEAN NOT NULL DEFAULT TRUE,
                balance_usd NUMERIC(18,6),
                daily_realized_pnl NUMERIC(18,6),
                daily_loss NUMERIC(18,6),
                total_spent_usd NUMERIC(18,6),
                total_spend_limit_usd NUMERIC(18,6),
                active_position_count INTEGER NOT NULL DEFAULT 0,
                active_exposure_usd NUMERIC(18,6),
                context_count INTEGER NOT NULL DEFAULT 0,
                market_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                near_miss_count INTEGER NOT NULL DEFAULT 0,
                entry_attempt_count INTEGER NOT NULL DEFAULT 0,
                stand_down_reason TEXT,
                top_rejection_reasons JSONB,
                guard_data JSONB,
                summary_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_merge_cycles_captured
            ON weather_merge_cycles (captured_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_merge_market_scans (
                id SERIAL PRIMARY KEY,
                cycle_id INTEGER NOT NULL REFERENCES weather_merge_cycles(id) ON DELETE CASCADE,
                captured_at TIMESTAMPTZ NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                market_id TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                qualifies BOOLEAN NOT NULL DEFAULT FALSE,
                combined_cost NUMERIC(18,6),
                combined_mid_cost NUMERIC(18,6),
                merge_edge NUMERIC(18,6),
                midpoint_edge NUMERIC(18,6),
                max_mergeable_size NUMERIC(18,6),
                inventory_imbalance_ratio NUMERIC(18,6),
                quote_age_seconds NUMERIC(18,6),
                yes_bid NUMERIC(18,6),
                yes_ask NUMERIC(18,6),
                no_bid NUMERIC(18,6),
                no_ask NUMERIC(18,6),
                yes_ask_size NUMERIC(18,6),
                no_ask_size NUMERIC(18,6),
                rejection_reasons JSONB,
                row_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_merge_market_scans_cycle
            ON weather_merge_market_scans (cycle_id, qualifies, market_id)
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
                bot_trade_id,
                signal_data,
                entry_detected_at
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27
            )
            RETURNING id
            """,
            plan["strategy_name"],
            plan["market_id"],
            plan["event_id"],
            plan["event_slug"],
            plan["city"],
            _date_value(plan.get("local_date")),
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
            None,
            json.dumps(plan.get("signal_data") or {}),
            datetime.now(timezone.utc),
        )
    return int(row["id"])


async def attach_bot_trade(position_id: int, bot_trade_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_merge_positions
            SET bot_trade_id = $2,
                last_checked_at = NOW()
            WHERE id = $1
            """,
            position_id,
            int(bot_trade_id),
        )


async def insert_weather_merge_cycle(
    *,
    captured_at: datetime,
    strategy_name: str,
    dry_run: bool,
    balance_usd: float,
    daily_realized_pnl: float,
    daily_loss: float,
    total_spent_usd: float,
    total_spend_limit_usd: float | None,
    active_position_count: int,
    active_exposure_usd: float,
    context_count: int,
    market_count: int,
    candidate_count: int,
    near_miss_count: int,
    entry_attempt_count: int,
    stand_down_reason: str | None,
    top_rejection_reasons: list[dict[str, Any]],
    guard_data: dict[str, Any],
    summary_data: dict[str, Any],
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_merge_cycles (
                captured_at,
                strategy_name,
                dry_run,
                balance_usd,
                daily_realized_pnl,
                daily_loss,
                total_spent_usd,
                total_spend_limit_usd,
                active_position_count,
                active_exposure_usd,
                context_count,
                market_count,
                candidate_count,
                near_miss_count,
                entry_attempt_count,
                stand_down_reason,
                top_rejection_reasons,
                guard_data,
                summary_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
            RETURNING id
            """,
            captured_at,
            strategy_name,
            dry_run,
            Decimal(str(round(balance_usd, 6))),
            Decimal(str(round(daily_realized_pnl, 6))),
            Decimal(str(round(daily_loss, 6))),
            Decimal(str(round(total_spent_usd, 6))),
            Decimal(str(round(total_spend_limit_usd, 6))) if total_spend_limit_usd is not None else None,
            int(active_position_count),
            Decimal(str(round(active_exposure_usd, 6))),
            int(context_count),
            int(market_count),
            int(candidate_count),
            int(near_miss_count),
            int(entry_attempt_count),
            stand_down_reason,
            json.dumps(top_rejection_reasons or []),
            json.dumps(guard_data or {}),
            json.dumps(summary_data or {}),
        )
    return int(row["id"])


async def insert_weather_merge_market_scans(
    cycle_id: int,
    rows: list[dict[str, Any]],
    *,
    captured_at: datetime,
) -> None:
    if not rows:
        return
    pool = get_pool()
    payload = []
    for row in rows:
        payload.append(
            (
                int(cycle_id),
                captured_at,
                str(row.get("event_id") or ""),
                str(row.get("event_slug") or ""),
                str(row.get("market_id") or ""),
                str(row.get("city") or ""),
                _date_value(row.get("local_date")),
                str(row.get("bucket_label") or ""),
                bool(row.get("qualifies")),
                Decimal(str(round(float(row.get("combined_cost") or 0.0), 6))) if row.get("combined_cost") is not None else None,
                Decimal(str(round(float(row.get("combined_mid_cost") or 0.0), 6))) if row.get("combined_mid_cost") is not None else None,
                Decimal(str(round(float(row.get("merge_edge") or 0.0), 6))) if row.get("merge_edge") is not None else None,
                Decimal(str(round(float(row.get("midpoint_edge") or 0.0), 6))) if row.get("midpoint_edge") is not None else None,
                Decimal(str(round(float(row.get("max_mergeable_size") or 0.0), 6))) if row.get("max_mergeable_size") is not None else None,
                Decimal(str(round(float(row.get("inventory_imbalance_ratio") or 0.0), 6))) if row.get("inventory_imbalance_ratio") is not None else None,
                Decimal(str(round(float(row.get("quote_age_seconds") or 0.0), 6))) if row.get("quote_age_seconds") is not None else None,
                Decimal(str(round(float(row.get("yes_bid") or 0.0), 6))) if row.get("yes_bid") is not None else None,
                Decimal(str(round(float(row.get("yes_ask") or 0.0), 6))) if row.get("yes_ask") is not None else None,
                Decimal(str(round(float(row.get("no_bid") or 0.0), 6))) if row.get("no_bid") is not None else None,
                Decimal(str(round(float(row.get("no_ask") or 0.0), 6))) if row.get("no_ask") is not None else None,
                Decimal(str(round(float(row.get("yes_ask_size") or 0.0), 6))) if row.get("yes_ask_size") is not None else None,
                Decimal(str(round(float(row.get("no_ask_size") or 0.0), 6))) if row.get("no_ask_size") is not None else None,
                json.dumps(row.get("rejection_reasons") or []),
                json.dumps(row, default=str),
            )
        )
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_merge_market_scans (
                cycle_id,
                captured_at,
                event_id,
                event_slug,
                market_id,
                city,
                local_date,
                bucket_label,
                qualifies,
                combined_cost,
                combined_mid_cost,
                merge_edge,
                midpoint_edge,
                max_mergeable_size,
                inventory_imbalance_ratio,
                quote_age_seconds,
                yes_bid,
                yes_ask,
                no_bid,
                no_ask,
                yes_ask_size,
                no_ask_size,
                rejection_reasons,
                row_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
            """,
            payload,
        )


async def insert_weather_merge_event(
    position_id: int,
    *,
    event_type: str,
    bot_trade_id: int | None = None,
    event_status: str | None = None,
    side: str | None = None,
    order_id: str | None = None,
    tx_hash: str | None = None,
    tx_mode: str | None = None,
    tx_state: str | None = None,
    shares: float | None = None,
    price: float | None = None,
    value_usdc: float | None = None,
    notes: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO weather_merge_position_events (
                position_id,
                bot_trade_id,
                event_type,
                event_status,
                side,
                order_id,
                tx_hash,
                tx_mode,
                tx_state,
                shares,
                price,
                value_usdc,
                notes,
                data
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14
            )
            """,
            position_id,
            int(bot_trade_id) if bot_trade_id is not None else None,
            event_type,
            event_status,
            side,
            order_id,
            tx_hash,
            tx_mode,
            tx_state,
            Decimal(str(round(shares, 6))) if shares is not None else None,
            Decimal(str(round(price, 6))) if price is not None else None,
            Decimal(str(round(value_usdc, 6))) if value_usdc is not None else None,
            notes,
            json.dumps(data) if data else None,
        )


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
