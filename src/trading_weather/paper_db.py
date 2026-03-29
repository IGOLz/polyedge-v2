"""Database helpers for the weather clone paper-trading runtime."""

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


def _decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), 6)))


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("quote_snapshot", "signal_data", "sequence_data", "raw_payload", "health_data", "summary_data"):
        value = item.get(key)
        if isinstance(value, str):
            try:
                item[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return item


async def create_weather_paper_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_positions (
                id SERIAL PRIMARY KEY,
                paper_run_id TEXT NOT NULL,
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
                target_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                filled_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                yes_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                no_shares NUMERIC(18,6) NOT NULL DEFAULT 0,
                avg_entry_price NUMERIC(12,6),
                total_entry_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
                realized_exit_value_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                signal_score NUMERIC(18,6),
                expected_edge_usd NUMERIC(18,6),
                config_fingerprint TEXT,
                git_sha TEXT,
                quote_snapshot JSONB,
                signal_data JSONB,
                sequence_data JSONB,
                entry_detected_at TIMESTAMPTZ,
                opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ,
                closed_at TIMESTAMPTZ,
                close_reason TEXT,
                notes TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_paper_positions_active
            ON weather_paper_positions (paper_run_id, status, playbook_key, market_id, opened_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_position_events (
                id SERIAL PRIMARY KEY,
                paper_run_id TEXT NOT NULL,
                position_id INTEGER NOT NULL REFERENCES weather_paper_positions(id) ON DELETE CASCADE,
                strategy_name TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                config_fingerprint TEXT,
                git_sha TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_weather_paper_position_events_position
            ON weather_paper_position_events (paper_run_id, position_id, occurred_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_cycles (
                id SERIAL PRIMARY KEY,
                paper_run_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                config_fingerprint TEXT,
                git_sha TEXT,
                fill_model TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                captured_at TIMESTAMPTZ NOT NULL,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                execution_health TEXT,
                market_data_health TEXT,
                quote_coverage_ratio NUMERIC(12,6),
                context_count INTEGER NOT NULL DEFAULT 0,
                market_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sequence_count INTEGER NOT NULL DEFAULT 0,
                entry_attempt_count INTEGER NOT NULL DEFAULT 0,
                fill_count INTEGER NOT NULL DEFAULT 0,
                partial_fill_count INTEGER NOT NULL DEFAULT 0,
                fill_notional_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                realized_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                unrealized_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                equity_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                top_rejection_reasons JSONB,
                health_data JSONB,
                summary_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_paper_cycles_captured
            ON weather_paper_cycles (paper_run_id, captured_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_market_scans (
                id SERIAL PRIMARY KEY,
                cycle_id INTEGER NOT NULL REFERENCES weather_paper_cycles(id) ON DELETE CASCADE,
                paper_run_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                config_fingerprint TEXT,
                git_sha TEXT,
                captured_at TIMESTAMPTZ NOT NULL,
                event_id TEXT NOT NULL,
                event_slug TEXT NOT NULL,
                market_id TEXT NOT NULL,
                city TEXT NOT NULL,
                local_date DATE,
                bucket_label TEXT NOT NULL,
                side TEXT,
                qualifies BOOLEAN NOT NULL DEFAULT FALSE,
                paper_eligible BOOLEAN NOT NULL DEFAULT FALSE,
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
            CREATE INDEX IF NOT EXISTS idx_weather_paper_market_scans_cycle
            ON weather_paper_market_scans (paper_run_id, cycle_id, playbook_key, qualifies)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_sequences (
                paper_run_id TEXT NOT NULL,
                sequence_key TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                playbook_key TEXT NOT NULL,
                config_fingerprint TEXT,
                git_sha TEXT,
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
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (paper_run_id, sequence_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_paper_sequences_playbook
            ON weather_paper_sequences (paper_run_id, playbook_key, state, last_seen_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_paper_equity_snapshots (
                id SERIAL PRIMARY KEY,
                paper_run_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                config_fingerprint TEXT,
                git_sha TEXT,
                captured_at TIMESTAMPTZ NOT NULL,
                realized_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                unrealized_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                equity_pnl_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                entry_notional_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                exit_notional_usd NUMERIC(18,6) NOT NULL DEFAULT 0,
                open_position_count INTEGER NOT NULL DEFAULT 0,
                mark_method TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_paper_equity_snapshots_run
            ON weather_paper_equity_snapshots (paper_run_id, captured_at DESC)
            """
        )


async def insert_paper_cycle(
    *,
    paper_run_id: str,
    strategy_name: str,
    config_fingerprint: str,
    git_sha: str | None,
    fill_model: str,
    execution_mode: str,
    captured_at: datetime,
    execution_allowed: bool,
    execution_health: str,
    market_data_health: str,
    quote_coverage_ratio: float,
    context_count: int,
    market_count: int,
    candidate_count: int,
    sequence_count: int,
    entry_attempt_count: int,
    fill_count: int,
    partial_fill_count: int,
    fill_notional_usd: float,
    realized_pnl_usd: float,
    unrealized_pnl_usd: float,
    equity_pnl_usd: float,
    top_rejection_reasons: list[dict[str, Any]],
    health_data: dict[str, Any],
    summary_data: dict[str, Any],
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_paper_cycles (
                paper_run_id,
                strategy_name,
                config_fingerprint,
                git_sha,
                fill_model,
                execution_mode,
                captured_at,
                execution_allowed,
                execution_health,
                market_data_health,
                quote_coverage_ratio,
                context_count,
                market_count,
                candidate_count,
                sequence_count,
                entry_attempt_count,
                fill_count,
                partial_fill_count,
                fill_notional_usd,
                realized_pnl_usd,
                unrealized_pnl_usd,
                equity_pnl_usd,
                top_rejection_reasons,
                health_data,
                summary_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
            RETURNING id
            """,
            paper_run_id,
            strategy_name,
            config_fingerprint,
            git_sha,
            fill_model,
            execution_mode,
            captured_at,
            execution_allowed,
            execution_health,
            market_data_health,
            _decimal(quote_coverage_ratio),
            int(context_count),
            int(market_count),
            int(candidate_count),
            int(sequence_count),
            int(entry_attempt_count),
            int(fill_count),
            int(partial_fill_count),
            _decimal(fill_notional_usd) or Decimal("0"),
            _decimal(realized_pnl_usd) or Decimal("0"),
            _decimal(unrealized_pnl_usd) or Decimal("0"),
            _decimal(equity_pnl_usd) or Decimal("0"),
            _json(top_rejection_reasons),
            _json(health_data),
            _json(summary_data),
        )
    return int(row["id"])


async def insert_paper_market_scans(
    cycle_id: int,
    rows: list[dict[str, Any]],
    *,
    paper_run_id: str,
    strategy_name: str,
    config_fingerprint: str,
    git_sha: str | None,
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
                paper_run_id,
                strategy_name,
                str(row.get("playbook_key") or ""),
                config_fingerprint,
                git_sha,
                captured_at,
                str(row.get("event_id") or ""),
                str(row.get("event_slug") or ""),
                str(row.get("market_id") or ""),
                str(row.get("city") or ""),
                row.get("local_date"),
                str(row.get("bucket_label") or ""),
                row.get("side"),
                bool(row.get("qualifies")),
                bool(row.get("paper_eligible")),
                _decimal(float(row.get("candidate_score") or 0.0)) or Decimal("0"),
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
            INSERT INTO weather_paper_market_scans (
                cycle_id,
                paper_run_id,
                strategy_name,
                playbook_key,
                config_fingerprint,
                git_sha,
                captured_at,
                event_id,
                event_slug,
                market_id,
                city,
                local_date,
                bucket_label,
                side,
                qualifies,
                paper_eligible,
                candidate_score,
                rejection_reasons,
                quote_snapshot,
                signal_data,
                sequence_data,
                health_data
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
            """,
            payload,
        )


async def upsert_paper_sequences(
    rows: list[dict[str, Any]],
    *,
    paper_run_id: str,
    strategy_name: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> None:
    if not rows:
        return
    pool = get_pool()
    payload = []
    for row in rows:
        payload.append(
            (
                paper_run_id,
                str(row["sequence_key"]),
                strategy_name,
                str(row["playbook_key"]),
                config_fingerprint,
                git_sha,
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
                _decimal(float(row.get("latest_candidate_score") or 0.0)) or Decimal("0"),
                _json(row.get("latest_rejection_reasons") or []),
                _json(row.get("latest_quote_snapshot") or {}),
                _json(row.get("latest_signal_data") or {}),
                _json(row.get("latest_health_data") or {}),
            )
        )
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO weather_paper_sequences (
                paper_run_id,
                sequence_key,
                strategy_name,
                playbook_key,
                config_fingerprint,
                git_sha,
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
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
            ON CONFLICT (paper_run_id, sequence_key) DO UPDATE SET
                strategy_name = EXCLUDED.strategy_name,
                playbook_key = EXCLUDED.playbook_key,
                config_fingerprint = EXCLUDED.config_fingerprint,
                git_sha = EXCLUDED.git_sha,
                market_id = EXCLUDED.market_id,
                event_id = EXCLUDED.event_id,
                event_slug = EXCLUDED.event_slug,
                city = EXCLUDED.city,
                local_date = EXCLUDED.local_date,
                bucket_label = EXCLUDED.bucket_label,
                side = EXCLUDED.side,
                state = EXCLUDED.state,
                first_seen_at = EXCLUDED.first_seen_at,
                first_qualifying_at = COALESCE(weather_paper_sequences.first_qualifying_at, EXCLUDED.first_qualifying_at),
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


async def insert_paper_position(
    *,
    paper_run_id: str,
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
    target_shares: float,
    signal_score: float,
    expected_edge_usd: float | None,
    config_fingerprint: str,
    git_sha: str | None,
    quote_snapshot: dict[str, Any],
    signal_data: dict[str, Any],
    sequence_data: dict[str, Any],
) -> int:
    pool = get_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_paper_positions (
                paper_run_id,
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
                target_shares,
                signal_score,
                expected_edge_usd,
                config_fingerprint,
                git_sha,
                quote_snapshot,
                signal_data,
                sequence_data,
                entry_detected_at,
                last_seen_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
            RETURNING id
            """,
            paper_run_id,
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
            _decimal(target_shares) or Decimal("0"),
            _decimal(signal_score) or Decimal("0"),
            _decimal(expected_edge_usd) if expected_edge_usd is not None else None,
            config_fingerprint,
            git_sha,
            _json(quote_snapshot),
            _json(signal_data),
            _json(sequence_data),
            now,
            now,
        )
    return int(row["id"])


async def insert_paper_position_event(
    position_id: int,
    *,
    paper_run_id: str,
    strategy_name: str,
    playbook_key: str,
    config_fingerprint: str,
    git_sha: str | None,
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
            INSERT INTO weather_paper_position_events (
                paper_run_id,
                position_id,
                strategy_name,
                playbook_key,
                config_fingerprint,
                git_sha,
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
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            RETURNING id
            """,
            paper_run_id,
            position_id,
            strategy_name,
            playbook_key,
            config_fingerprint,
            git_sha,
            event_type,
            status,
            side,
            _decimal(target_shares),
            _decimal(filled_shares),
            _decimal(price),
            _decimal(value_usd),
            order_id,
            tx_hash,
            reason,
            notes,
            _json(raw_payload),
        )
    return int(row["id"])


async def get_open_paper_positions(*, paper_run_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM weather_paper_positions
            WHERE paper_run_id = $1
              AND closed_at IS NULL
            ORDER BY opened_at ASC
            """,
            paper_run_id,
        )
    return [_decode_row(dict(row)) for row in rows]


async def get_paper_entry_activity(
    *,
    paper_run_id: str,
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
            FROM weather_paper_positions
            WHERE paper_run_id = $1
              AND opened_at >= $2
              AND condition_id = $3
              AND playbook_key = $4
              AND COALESCE(side, 'paired') = $5
            """,
            paper_run_id,
            window_start,
            condition_id,
            playbook_key,
            normalized_side,
        )
    return {
        "entry_count": int(row["entry_count"] or 0) if row else 0,
        "latest_opened_at": row["latest_opened_at"] if row else None,
    }


async def update_paper_position_fill(
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
            UPDATE weather_paper_positions
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
            _decimal(filled_shares) or Decimal("0"),
            _decimal(avg_entry_price) or Decimal("0"),
            _decimal(total_entry_cost) or Decimal("0"),
            _decimal(yes_shares) or Decimal("0"),
            _decimal(no_shares) or Decimal("0"),
            status,
            notes,
        )


async def update_paper_position_inventory(
    position_id: int,
    *,
    yes_shares: float,
    no_shares: float,
    filled_shares: float,
    realized_exit_value_usd: float | None = None,
    status: str,
    close_reason: str | None = None,
    notes: str | None = None,
    close_position: bool = False,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE weather_paper_positions
            SET yes_shares = $2,
                no_shares = $3,
                filled_shares = $4,
                realized_exit_value_usd = COALESCE($5, realized_exit_value_usd),
                status = $6,
                close_reason = COALESCE($7, close_reason),
                notes = COALESCE($8, notes),
                last_seen_at = NOW(),
                closed_at = CASE WHEN $9 THEN NOW() ELSE closed_at END
            WHERE id = $1
            """,
            position_id,
            _decimal(yes_shares) or Decimal("0"),
            _decimal(no_shares) or Decimal("0"),
            _decimal(filled_shares) or Decimal("0"),
            _decimal(realized_exit_value_usd),
            status,
            close_reason,
            notes,
            close_position,
        )


async def get_paper_daily_spend_usd(*, paper_run_id: str, day_start: datetime | None = None) -> float:
    window_start = _utc_day_start(day_start)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(total_entry_cost), 0) AS gross_spend
            FROM weather_paper_positions
            WHERE paper_run_id = $1
              AND opened_at >= $2
              AND total_entry_cost > 0
            """,
            paper_run_id,
            window_start,
        )
    return float(row["gross_spend"] or 0.0) if row else 0.0


async def get_paper_daily_realized_pnl(*, paper_run_id: str, day_start: datetime | None = None) -> float:
    window_start = _utc_day_start(day_start)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(COALESCE(realized_exit_value_usd, 0) - COALESCE(total_entry_cost, 0)), 0) AS realized_pnl
            FROM weather_paper_positions
            WHERE paper_run_id = $1
              AND closed_at >= $2
            """,
            paper_run_id,
            window_start,
        )
    return float(row["realized_pnl"] or 0.0) if row else 0.0


async def get_paper_run_totals(*, paper_run_id: str) -> dict[str, float]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(total_entry_cost), 0) AS entry_notional_usd,
                COALESCE(SUM(realized_exit_value_usd), 0) AS exit_notional_usd
            FROM weather_paper_positions
            WHERE paper_run_id = $1
            """,
            paper_run_id,
        )
    return {
        "entry_notional_usd": float(row["entry_notional_usd"] or 0.0) if row else 0.0,
        "exit_notional_usd": float(row["exit_notional_usd"] or 0.0) if row else 0.0,
    }


async def close_paper_position(
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
            UPDATE weather_paper_positions
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
            _decimal(realized_exit_value_usd),
            notes,
        )


async def insert_paper_equity_snapshot(
    *,
    paper_run_id: str,
    strategy_name: str,
    config_fingerprint: str,
    git_sha: str | None,
    captured_at: datetime,
    realized_pnl_usd: float,
    unrealized_pnl_usd: float,
    equity_pnl_usd: float,
    entry_notional_usd: float,
    exit_notional_usd: float,
    open_position_count: int,
    mark_method: str,
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_paper_equity_snapshots (
                paper_run_id,
                strategy_name,
                config_fingerprint,
                git_sha,
                captured_at,
                realized_pnl_usd,
                unrealized_pnl_usd,
                equity_pnl_usd,
                entry_notional_usd,
                exit_notional_usd,
                open_position_count,
                mark_method
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            paper_run_id,
            strategy_name,
            config_fingerprint,
            git_sha,
            captured_at,
            _decimal(realized_pnl_usd) or Decimal("0"),
            _decimal(unrealized_pnl_usd) or Decimal("0"),
            _decimal(equity_pnl_usd) or Decimal("0"),
            _decimal(entry_notional_usd) or Decimal("0"),
            _decimal(exit_notional_usd) or Decimal("0"),
            int(open_position_count),
            mark_method,
        )
    return int(row["id"])
