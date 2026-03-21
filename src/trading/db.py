"""Trading-specific database layer — bot_trades, bot_logs, bot_config tables.

Extends shared.db with trading-specific tables and queries.
Uses the same asyncpg pool from shared.db.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from shared.db import get_pool

logger = logging.getLogger("polyedge.trading")


# ── Schema ──────────────────────────────────────────────────────────────

async def create_trading_tables() -> None:
    """Create bot_trades, bot_logs, bot_config tables."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_trades (
                id              SERIAL PRIMARY KEY,
                market_id       TEXT NOT NULL,
                market_type     TEXT NOT NULL,
                strategy_name   TEXT NOT NULL,
                direction       TEXT NOT NULL,
                entry_price     NUMERIC(6,4) NOT NULL,
                bet_size_usd    NUMERIC(10,2) NOT NULL,
                shares          NUMERIC(10,4),
                token_id        TEXT,
                condition_id    TEXT,
                status          TEXT NOT NULL,
                order_id        TEXT,
                placed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at     TIMESTAMPTZ,
                final_outcome   TEXT,
                pnl             NUMERIC(10,2),
                notes           TEXT,
                redeemed        BOOLEAN NOT NULL DEFAULT FALSE,
                confidence_multiplier NUMERIC(4,2) DEFAULT 1.0,
                stop_loss_order_id TEXT,
                stop_loss_price NUMERIC(6,4),
                stop_loss_triggered BOOLEAN DEFAULT FALSE,
                signal_data     JSONB,
                execution_stage TEXT,
                locked_entry_price NUMERIC(10,6),
                locked_shares   NUMERIC(10,4),
                locked_cost     NUMERIC(10,4),
                locked_balance  NUMERIC(10,2),
                price_variance  NUMERIC(10,6),
                price_variance_pct NUMERIC(10,4),
                shares_variance INTEGER,
                signal_generated_at TIMESTAMPTZ,
                signal_age_seconds NUMERIC(10,4)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_logs (
                id          SERIAL PRIMARY KEY,
                logged_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                log_type    TEXT NOT NULL,
                message     TEXT NOT NULL,
                data        JSONB
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_mode TEXT"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_transaction_id TEXT"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_tx_hash TEXT"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_state TEXT"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_attempted_at TIMESTAMPTZ"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS redemption_error TEXT"
        )
        await conn.execute(
            "ALTER TABLE bot_trades ADD COLUMN IF NOT EXISTS amount_redeemed NUMERIC(10,6)"
        )
    logger.info("Trading database tables ready.")


# ── Data classes ────────────────────────────────────────────────────────

@dataclass
class MarketInfo:
    market_id: str
    market_type: str
    started_at: datetime
    ended_at: datetime
    up_token_id: str | None = None
    down_token_id: str | None = None


@dataclass
class Tick:
    market_id: str
    time: datetime
    up_price: float
    down_price: float

    def __post_init__(self):
        if self.down_price == 0.0:
            self.down_price = round(1.0 - self.up_price, 6)


@dataclass
class UnresolvedTrade:
    id: int
    market_id: str
    market_type: str
    strategy_name: str
    direction: str
    entry_price: float
    bet_size_usd: float
    token_id: str | None
    condition_id: str | None


@dataclass
class BotStats:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    fok_no_fills: int = 0
    total_pnl: float = 0.0
    roi: float = 0.0
    daily_net_loss_today: float = 0.0
    pending_redemption: float = 0.0
    strategies_active: list[str] | None = None


# ── Live config ────────────────────────────────────────────────────────

async def seed_config_if_empty(defaults: dict[str, str]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        for key, value in defaults.items():
            await conn.execute("""
                INSERT INTO bot_config (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO NOTHING
            """, key.lower(), value)


async def get_live_config() -> dict[str, str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM bot_config")
        return {row['key'].lower(): row['value'] for row in rows}


# ── Market queries (using shared.db for tick/outcome data) ──────────────

async def get_active_markets() -> list[MarketInfo]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT market_id, market_type, started_at, ended_at
            FROM market_outcomes
            WHERE ended_at > NOW() AND resolved = FALSE
            ORDER BY started_at ASC
        """)
    return [MarketInfo(**dict(r)) for r in rows]


async def get_market_ticks(market_id: str, started_at: datetime, limit: int = 300) -> list[Tick]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT market_id, time, up_price FROM market_ticks
            WHERE market_id = $1 AND time >= $2
            ORDER BY time ASC LIMIT $3
        """, market_id, started_at, limit)
    return [
        Tick(
            market_id=r["market_id"],
            time=r["time"],
            up_price=float(r["up_price"]),
            down_price=round(1.0 - float(r["up_price"]), 6),
        )
        for r in rows
    ]


async def already_traded_this_market(market_id: str, strategy_name: str | None = None) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        if strategy_name:
            row = await conn.fetchrow(
                "SELECT 1 FROM bot_trades WHERE market_id=$1 AND strategy_name=$2 LIMIT 1",
                market_id, strategy_name)
        else:
            row = await conn.fetchrow(
                "SELECT 1 FROM bot_trades WHERE market_id=$1 LIMIT 1", market_id)
    return row is not None


async def get_price_at_second(market_id: str, started_at: datetime, seconds: int) -> float | None:
    from datetime import timedelta
    target = started_at + timedelta(seconds=seconds)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT up_price FROM market_ticks
            WHERE market_id = $1 AND time BETWEEN $2 AND $3
            ORDER BY ABS(EXTRACT(EPOCH FROM (time - $4))) LIMIT 1
        """, market_id, target - timedelta(seconds=10), target + timedelta(seconds=10), target)
    return float(row["up_price"]) if row else None


# ── Trade insertion/update ──────────────────────────────────────────────

async def insert_bot_trade(*, market_id, market_type, strategy_name, direction,
                           entry_price, bet_size_usd, shares=None, token_id=None,
                           condition_id=None, status, order_id=None, notes=None,
                           signal_data=None, execution_stage=None,
                           locked_entry_price=None, locked_shares_count=None,
                           locked_cost=None, locked_balance=None,
                           price_variance_val=None, price_variance_pct_val=None,
                           shares_variance_count=None, signal_generated_at=None,
                           signal_age_seconds=None) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO bot_trades
                (market_id, market_type, strategy_name, direction,
                 entry_price, bet_size_usd, shares, token_id,
                 condition_id, status, order_id, notes, signal_data,
                 execution_stage,
                 locked_entry_price, locked_shares, locked_cost, locked_balance,
                 price_variance, price_variance_pct, shares_variance,
                 signal_generated_at, signal_age_seconds)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                    $15,$16,$17,$18,$19,$20,$21,$22,$23)
            RETURNING id
        """,
            market_id, market_type, strategy_name, direction,
            Decimal(str(entry_price)), Decimal(str(bet_size_usd)),
            Decimal(str(shares)) if shares is not None else None,
            token_id, condition_id, status, order_id, notes,
            json.dumps(signal_data) if signal_data else None,
            execution_stage,
            Decimal(str(locked_entry_price)) if locked_entry_price is not None else None,
            Decimal(str(locked_shares_count)) if locked_shares_count is not None else None,
            Decimal(str(locked_cost)) if locked_cost is not None else None,
            Decimal(str(locked_balance)) if locked_balance is not None else None,
            Decimal(str(round(price_variance_val, 6))) if price_variance_val is not None else None,
            Decimal(str(round(price_variance_pct_val, 4))) if price_variance_pct_val is not None else None,
            shares_variance_count,
            signal_generated_at,
            Decimal(str(signal_age_seconds)) if signal_age_seconds is not None else None,
        )
    return row["id"]


async def update_pending_outcomes(clob=None) -> list[dict]:
    pool = get_pool()
    # Identify trades to resolve
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT bt.id, bt.market_id, bt.market_type, bt.strategy_name,
                   bt.direction, bt.entry_price, bt.bet_size_usd, bt.shares,
                   mo.final_outcome AS market_outcome
            FROM bot_trades bt
            JOIN market_outcomes mo ON bt.market_id = mo.market_id
            WHERE bt.status = 'filled' AND bt.final_outcome IS NULL
              AND mo.resolved = TRUE AND mo.final_outcome IS NOT NULL
        """)

    # Bulk resolve
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE bot_trades bt SET
                final_outcome = CASE
                    WHEN mo.final_outcome = bt.direction THEN 'win'
                    WHEN mo.final_outcome IS NOT NULL AND mo.final_outcome != bt.direction THEN 'loss'
                END,
                resolved_at = NOW(),
                pnl = CASE
                    WHEN mo.final_outcome = bt.direction
                        THEN COALESCE(bt.shares, bt.bet_size_usd / NULLIF(bt.entry_price, 0)) * (1.0 - bt.entry_price)
                    WHEN mo.final_outcome IS NOT NULL AND mo.final_outcome != bt.direction
                        THEN -bt.bet_size_usd
                END
            FROM market_outcomes mo
            WHERE bt.market_id = mo.market_id
              AND bt.status = 'filled' AND bt.final_outcome IS NULL
              AND mo.resolved = TRUE AND mo.final_outcome IS NOT NULL
        """)

    resolved: list[dict] = []
    for r in pending:
        entry = float(r["entry_price"])
        bet_size = float(r["bet_size_usd"])
        shares = float(r["shares"]) if r["shares"] is not None else (bet_size / entry if entry else 0)
        market_outcome = r["market_outcome"]
        won = market_outcome == r["direction"]
        pnl = shares * (1.0 - entry) if won else -bet_size
        resolved.append({
            "trade_id": r["id"], "market_id": r["market_id"],
            "market_type": r["market_type"], "strategy_name": r["strategy_name"],
            "direction": r["direction"], "entry_price": entry,
            "bet_size_usd": bet_size, "shares": shares,
            "market_outcome": market_outcome,
            "result": "win" if won else "loss", "pnl": round(pnl, 2),
        })

    return resolved


# ── Stop-loss helpers ──────────────────────────────────────────────────

async def update_stop_loss_order(trade_id: int, order_id: str, stop_loss_price: float) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE bot_trades SET stop_loss_order_id=$1, stop_loss_price=$2 WHERE id=$3
        """, order_id, Decimal(str(round(stop_loss_price, 4))), trade_id)


async def mark_stop_loss_triggered(trade_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE bot_trades SET stop_loss_triggered=TRUE, final_outcome='stop_loss',
                resolved_at=NOW(),
                pnl=(COALESCE(stop_loss_price,0)-entry_price)*COALESCE(shares,bet_size_usd/NULLIF(entry_price,0))
            WHERE id=$1
        """, trade_id)


async def mark_stop_loss_cancelled(trade_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE bot_trades SET stop_loss_order_id=NULL WHERE id=$1", trade_id)


async def get_open_stop_loss_orders() -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT id, market_id, market_type, strategy_name, stop_loss_order_id,
                   token_id, direction, entry_price, shares, bet_size_usd, stop_loss_price
            FROM bot_trades
            WHERE stop_loss_order_id IS NOT NULL AND stop_loss_triggered=FALSE
              AND final_outcome IS NULL AND status='filled'
        """)


async def get_unredeemed_fills() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT bt.market_id, bt.condition_id, bt.token_id, bt.bet_size_usd
            FROM bot_trades bt JOIN market_outcomes mo ON bt.market_id=mo.market_id
            WHERE bt.status='filled' AND bt.final_outcome='win' AND bt.redeemed=FALSE
              AND bt.condition_id IS NOT NULL AND bt.condition_id != '' AND mo.resolved=TRUE
        """)
    return [dict(r) for r in rows]


async def mark_redeemed(condition_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE bot_trades SET redeemed=TRUE WHERE condition_id=$1", condition_id)


async def record_redemption_success(
    condition_id: str,
    *,
    mode: str,
    transaction_id: str | None,
    transaction_hash: str | None,
    state: str | None,
    amount_redeemed: float,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bot_trades
            SET redeemed=TRUE,
                redemption_mode=$2,
                redemption_transaction_id=$3,
                redemption_tx_hash=$4,
                redemption_state=$5,
                redemption_attempted_at=NOW(),
                redemption_error=NULL,
                amount_redeemed=$6
            WHERE condition_id=$1
            """,
            condition_id,
            mode,
            transaction_id,
            transaction_hash,
            state,
            Decimal(str(round(amount_redeemed, 6))),
        )


async def record_redemption_failure(condition_id: str, error_message: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bot_trades
            SET redemption_attempted_at=NOW(),
                redemption_error=$2
            WHERE condition_id=$1
            """,
            condition_id,
            error_message[:1000],
        )


# ── Logging ─────────────────────────────────────────────────────────────

async def log_event(log_type: str, message: str, data: dict | None = None) -> None:
    logger.info(message)
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO bot_logs (log_type, message, data) VALUES ($1, $2, $3)
            """, log_type, message, json.dumps(data) if data else None)
    except Exception as e:
        logger.warning("Failed to write bot_log: %s", e)


async def get_bot_stats() -> BotStats:
    stats = BotStats()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status='filled') AS total_trades,
                    COUNT(*) FILTER (WHERE final_outcome='win') AS wins,
                    COUNT(*) FILTER (WHERE final_outcome='loss') AS losses,
                    COUNT(*) FILTER (WHERE status='fok_no_fill') AS fok_no_fills,
                    COALESCE(SUM(pnl) FILTER (WHERE final_outcome IS NOT NULL), 0) AS total_pnl,
                    COALESCE(SUM(bet_size_usd) FILTER (WHERE status='filled'), 0) AS total_wagered
                FROM bot_trades WHERE placed_at > NOW() - INTERVAL '24 hours'
            """)
            if row:
                stats.total_trades = row["total_trades"]
                stats.wins = row["wins"]
                stats.losses = row["losses"]
                stats.fok_no_fills = row["fok_no_fills"]
                stats.total_pnl = float(row["total_pnl"])
                wagered = float(row["total_wagered"])
                stats.roi = (stats.total_pnl / wagered * 100) if wagered > 0 else 0.0
    except Exception:
        logger.exception("Failed to compute bot stats")
    return stats
