"""Database helpers for the ColdMath weather clone runtime."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from shared.db import get_pool


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _utc_day_start(day_start: datetime | None = None) -> datetime:
    current = day_start or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return current.replace(hour=0, minute=0, second=0, microsecond=0)


async def create_weather_clone_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_clone_positions (
                id SERIAL PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                market_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                side TEXT,
                condition_id TEXT NOT NULL,
                neg_risk BOOLEAN NOT NULL DEFAULT FALSE,
                yes_token_id TEXT,
                no_token_id TEXT,
                status TEXT NOT NULL,
                shadow_only BOOLEAN NOT NULL DEFAULT TRUE,
                target_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                filled_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                yes_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                no_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                avg_entry_price NUMERIC(12,6),
                total_entry_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
                signal_score NUMERIC(18,6),
                expected_edge_usd NUMERIC(18,6),
                quote_snapshot JSONB,
                signal_data JSONB,
                sequence_data JSONB,
                entry_detected_at TIMESTAMPTZ,
                opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ,
                closed_at TIMESTAMPTZ,
                close_reason TEXT,
                realized_exit_value_usd NUMERIC(18,6),
                notes TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_clone_positions_active
            ON weather_clone_positions (status, playbook_key, market_id, opened_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_clone_position_events (
                id SERIAL PRIMARY KEY,
                position_id INTEGER NOT NULL REFERENCES weather_clone_positions(id) ON DELETE CASCADE,
                playbook_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT,
                side TEXT,
                target_shares NUMERIC(18,6),
                filled_shares NUMERIC(18,6),
                price NUMERIC(12,6),
                value_usd NUMERIC(18,6),
                order_id TEXT,
                tx_hash TEXT,
                reason TEXT,
                notes TEXT,
                raw_payload JSONB,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_clone_position_events_position
            ON weather_clone_position_events (position_id, occurred_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_clone_cycles (
                id SERIAL PRIMARY KEY,
                captured_at TIMESTAMPTZ NOT NULL,
                strategy_name TEXT NOT NULL,
                dry_run BOOLEAN NOT NULL DEFAULT TRUE,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                execution_health TEXT,
                market_data_health TEXT,
                quote_coverage_ratio NUMERIC(12,6),
                context_count INTEGER NOT NULL DEFAULT 0,
                market_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sequence_count INTEGER NOT NULL DEFAULT 0,
                entry_attempt_count INTEGER NOT NULL DEFAULT 0,
                top_rejection_reasons JSONB,
                health_data JSONB,
                summary_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_clone_cycles_captured
            ON weather_clone_cycles (captured_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_clone_market_scans (
                id SERIAL PRIMARY KEY,
                cycle_id INTEGER NOT NULL REFERENCES weather_clone_cycles(id) ON DELETE CASCADE,
                captured_at TIMESTAMPTZ NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                market_id TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                side TEXT,
                qualifies BOOLEAN NOT NULL DEFAULT FALSE,
                live_eligible BOOLEAN NOT NULL DEFAULT FALSE,
                candidate_score NUMERIC(18,6),
                rejection_reasons JSONB,
                quote_snapshot JSONB,
                signal_data JSONB,
                sequence_data JSONB,
                health_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_clone_market_scans_cycle
            ON weather_clone_market_scans (cycle_id, playbook_key, qualifies)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_clone_sequences (
                sequence_key TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                market_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                side TEXT,
                state TEXT NOT NULL,
                first_seen_at TIMESTAMPTZ NOT NULL,
                first_qualifying_at TIMESTAMPTZ,
                last_seen_at TIMESTAMPTZ NOT NULL,
                last_qualifying_at TIMESTAMPTZ,
                detection_count INTEGER NOT NULL DEFAULT 0,
                qualify_count INTEGER NOT NULL DEFAULT 0,
                latest_candidate_score NUMERIC(18,6),
                latest_rejection_reasons JSONB,
                latest_quote_snapshot JSONB,
                latest_signal_data JSONB,
                latest_health_data JSONB,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_clone_sequences_playbook
            ON weather_clone_sequences (playbook_key, state, last_seen_at DESC)
            """
        )


async def insert_clone_cycle(
    *,
    captured_at: datetime,
    strategy_name: str,
    dry_run: bool,
    execution_allowed: bool,
    execution_health: str,
    market_data_health: str,
    quote_coverage_ratio: float,
    context_count: int,
    market_count: int,
    candidate_count: int,
    sequence_count: int,
    entry_attempt_count: int,
    top_rejection_reasons: list[dict[str, Any]],
    health_data: dict[str, Any],
    summary_data: dict[str, Any],
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_clone_cycles (
                captured_at,
                strategy_name,
                dry_run,
                execution_allowed,
                execution_health,
                market_data_health,
                quote_coverage_ratio,
                context_count,
                market_count,
                candidate_count,
                sequence_count,
                entry_attempt_count,
                top_rejection_reasons,
                health_data,
                summary_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            RETURNING id
            """,
            captured_at,
            strategy_name,
            dry_run,
            execution_allowed,
            execution_health,
            market_data_health,
            Decimal(str(round(quote_coverage_ratio, 6))),
            int(context_count),
            int(market_count),
            int(candidate_count),
            int(sequence_count),
            int(entry_attempt_count),
            _json(top_rejection_reasons),
            _json(health_data),
            _json(summary_data),
        )
    return int(row["id"])


async def insert_clone_market_scans(
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
                cycle_id,
                captured_at,
                str(row.get("event_id") or ""),
                str(row.get("event_slug") or ""),
                str(row.get("market_id") or ""),
                str(row.get("city") or ""),
                row.get("local_date"),
                str(row.get("bucket_label") or ""),
                str(row.get("playbook_key") or ""),
                row.get("side"),
                bool(row.get("qualifies")),
                bool(row.get("live_eligible")),
                Decimal(str(round(float(row.get("candidate_score") or 0.0), 6))),
                _json(row.get("rejection_reasons") or []),
                _json(row.get("quote_snapshot") or {}),
                _json(row.get("signal_data") or {}),
                _json(row.get("sequence_data") or {}),
                _json(row.get("health_data") or {}),
            )
        )
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_clone_market_scans (
                cycle_id,
                captured_at,
                event_id,
                event_slug,
                market_id,
                city,
                local_date,
                bucket_label,
                playbook_key,
                side,
                qualifies,
                live_eligible,
                candidate_score,
                rejection_reasons,
                quote_snapshot,
                signal_data,
                sequence_data,
                health_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            """,
            payload,
        )


async def upsert_clone_sequences(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    pool = get_pool()
    payload = []
    for row in rows:
        payload.append(
            (
                str(row["sequence_key"]),
                str(row["strategy_name"]),
                str(row["playbook_key"]),
                str(row["market_id"]),
                str(row["event_id"]),
                str(row["event_slug"]),
                str(row["city"]),
                row.get("local_date"),
                str(row["bucket_label"]),
                row.get("side"),
                str(row["state"]),
                row["first_seen_at"],
                row.get("first_qualifying_at"),
                row["last_seen_at"],
                row.get("last_qualifying_at"),
                int(row.get("detection_count") or 0),
                int(row.get("qualify_count") or 0),
                Decimal(str(round(float(row.get("latest_candidate_score") or 0.0), 6))),
                _json(row.get("latest_rejection_reasons") or []),
                _json(row.get("latest_quote_snapshot") or {}),
                _json(row.get("latest_signal_data") or {}),
                _json(row.get("latest_health_data") or {}),
            )
        )
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_clone_sequences (
                sequence_key,
                strategy_name,
                playbook_key,
                market_id,
                event_id,
                event_slug,
                city,
                local_date,
                bucket_label,
                side,
                state,
                first_seen_at,
                first_qualifying_at,
                last_seen_at,
                last_qualifying_at,
                detection_count,
                qualify_count,
                latest_candidate_score,
                latest_rejection_reasons,
                latest_quote_snapshot,
                latest_signal_data,
                latest_health_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
            ON CONFLICT (sequence_key) DO UPDATE SET
                strategy_name = EXCLUDED.strategy_name,
                playbook_key = EXCLUDED.playbook_key,
                market_id = EXCLUDED.market_id,
                event_id = EXCLUDED.event_id,
                event_slug = EXCLUDED.event_slug,
                city = EXCLUDED.city,
                local_date = EXCLUDED.local_date,
                bucket_label = EXCLUDED.bucket_label,
                side = EXCLUDED.side,
                state = EXCLUDED.state,
                first_seen_at = EXCLUDED.first_seen_at,
                first_qualifying_at = COALESCE(weather_clone_sequences.first_qualifying_at, EXCLUDED.first_qualifying_at),
                last_seen_at = EXCLUDED.last_seen_at,
                last_qualifying_at = EXCLUDED.last_qualifying_at,
                detection_count = EXCLUDED.detection_count,
                qualify_count = EXCLUDED.qualify_count,
                latest_candidate_score = EXCLUDED.latest_candidate_score,
                latest_rejection_reasons = EXCLUDED.latest_rejection_reasons,
                latest_quote_snapshot = EXCLUDED.latest_quote_snapshot,
                latest_signal_data = EXCLUDED.latest_signal_data,
                latest_health_data = EXCLUDED.latest_health_data,
                updated_at = NOW()
            """,
            payload,
        )


async def insert_clone_position(
    *,
    strategy_name: str,
    playbook_key: str,
    market_id: str,
    event_id: str,
    event_slug: str,
    city: str,
    local_date,
    bucket_label: str,
    side: str | None,
    condition_id: str,
    neg_risk: bool,
    yes_token_id: str | None,
    no_token_id: str | None,
    status: str,
    shadow_only: bool,
    target_shares: float,
    signal_score: float,
    expected_edge_usd: float | None,
    quote_snapshot: dict[str, Any],
    signal_data: dict[str, Any],
    sequence_data: dict[str, Any],
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_clone_positions (
                strategy_name,
                playbook_key,
                market_id,
                event_id,
                event_slug,
                city,
                local_date,
                bucket_label,
                side,
                condition_id,
                neg_risk,
                yes_token_id,
                no_token_id,
                status,
                shadow_only,
                target_shares,
                signal_score,
                expected_edge_usd,
                quote_snapshot,
                signal_data,
                sequence_data,
                entry_detected_at,
                last_seen_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
            RETURNING id
            """,
            strategy_name,
            playbook_key,
            market_id,
            event_id,
            event_slug,
            city,
            local_date,
            bucket_label,
            side,
            condition_id,
            neg_risk,
            yes_token_id,
            no_token_id,
            status,
            shadow_only,
            Decimal(str(round(target_shares, 6))),
            Decimal(str(round(signal_score, 6))),
            Decimal(str(round(expected_edge_usd or 0.0, 6))) if expected_edge_usd is not None else None,
            _json(quote_snapshot),
            _json(signal_data),
            _json(sequence_data),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )
    return int(row["id"])


async def insert_clone_position_event(
    position_id: int,
    *,
    playbook_key: str,
    event_type: str,
    status: str | None = None,
    side: str | None = None,
    target_shares: float | None = None,
    filled_shares: float | None = None,
    price: float | None = None,
    value_usd: float | None = None,
    order_id: str | None = None,
    tx_hash: str | None = None,
    reason: str | None = None,
    notes: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_clone_position_events (
                position_id,
                playbook_key,
                event_type,
                status,
                side,
                target_shares,
                filled_shares,
                price,
                value_usd,
                order_id,
                tx_hash,
                reason,
                notes,
                raw_payload
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            RETURNING id
            """,
            position_id,
            playbook_key,
            event_type,
            status,
            side,
            Decimal(str(round(target_shares, 6))) if target_shares is not None else None,
            Decimal(str(round(filled_shares, 6))) if filled_shares is not None else None,
            Decimal(str(round(price, 6))) if price is not None else None,
            Decimal(str(round(value_usd, 6))) if value_usd is not None else None,
            order_id,
            tx_hash,
            reason,
            notes,
            _json(raw_payload),
        )
    return int(row["id"])


async def get_open_clone_positions() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM weather_clone_positions
            WHERE closed_at IS NULL
            ORDER BY opened_at ASC
            """
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("quote_snapshot", "signal_data", "sequence_data"):
            value = item.get(key)
            if isinstance(value, str):
                try:
                    item[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        result.append(item)
    return result


async def get_clone_entry_activity(
    *,
    condition_id: str,
    playbook_key: str,
    side: str,
    day_start: datetime | None = None,
) -> dict[str, Any]:
    window_start = _utc_day_start(day_start)
    normalized_side = str(side or "").strip() or "paired"
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS entry_count,
                MAX(opened_at) AS latest_opened_at
            FROM weather_clone_positions
            WHERE shadow_only = FALSE
              AND opened_at >= $1
              AND condition_id = $2
              AND playbook_key = $3
              AND COALESCE(side, 'paired') = $4
            """,
            window_start,
            condition_id,
            playbook_key,
            normalized_side,
        )
    return {
        "entry_count": int(row["entry_count"] or 0) if row else 0,
        "latest_opened_at": row["latest_opened_at"] if row else None,
    }


async def update_clone_position_fill(
    position_id: int,
    *,
    filled_shares: float,
    avg_entry_price: float,
    total_entry_cost: float,
    yes_shares: float,
    no_shares: float,
    status: str,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_clone_positions
            SET filled_shares = $2,
                avg_entry_price = $3,
                total_entry_cost = $4,
                yes_shares = $5,
                no_shares = $6,
                status = $7,
                notes = COALESCE($8, notes),
                last_seen_at = NOW()
            WHERE id = $1
            """,
            position_id,
            Decimal(str(round(filled_shares, 6))),
            Decimal(str(round(avg_entry_price, 6))),
            Decimal(str(round(total_entry_cost, 6))),
            Decimal(str(round(yes_shares, 6))),
            Decimal(str(round(no_shares, 6))),
            status,
            notes,
        )


async def get_clone_daily_spend_usd(day_start: datetime | None = None) -> float:
    window_start = _utc_day_start(day_start)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(total_entry_cost), 0) AS gross_spend
            FROM weather_clone_positions
            WHERE shadow_only = FALSE
              AND opened_at >= $1
              AND total_entry_cost > 0
            """,
            window_start,
        )
    return float(row["gross_spend"] or 0.0) if row else 0.0


async def get_clone_daily_realized_pnl(day_start: datetime | None = None) -> float:
    window_start = _utc_day_start(day_start)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(COALESCE(realized_exit_value_usd, 0) - COALESCE(total_entry_cost, 0)), 0) AS realized_pnl
            FROM weather_clone_positions
            WHERE shadow_only = FALSE
              AND closed_at >= $1
              AND realized_exit_value_usd IS NOT NULL
            """,
            window_start,
        )
    return float(row["realized_pnl"] or 0.0) if row else 0.0


async def close_clone_position(
    position_id: int,
    *,
    status: str,
    close_reason: str,
    realized_exit_value_usd: float | None = None,
    notes: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_clone_positions
            SET status = $2,
                close_reason = $3,
                realized_exit_value_usd = COALESCE($4, realized_exit_value_usd),
                notes = COALESCE($5, notes),
                last_seen_at = NOW(),
                closed_at = NOW()
            WHERE id = $1
            """,
            position_id,
            status,
            close_reason,
            Decimal(str(round(realized_exit_value_usd, 6))) if realized_exit_value_usd is not None else None,
            notes,
        )
