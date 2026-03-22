"""Persistence helpers for wallet-forensics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg2.extras import Json, RealDictCursor, execute_values

from analysis.wallet_forensics.utils import row_hash


def upsert_wallet_target(conn, target: dict[str, Any]) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO wallet_targets (
                proxy_wallet,
                profile_name,
                pseudonym,
                bio,
                display_username_public,
                created_at,
                total_traded_markets,
                source_profile_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (proxy_wallet) DO UPDATE SET
                profile_name = EXCLUDED.profile_name,
                pseudonym = EXCLUDED.pseudonym,
                bio = EXCLUDED.bio,
                display_username_public = EXCLUDED.display_username_public,
                created_at = COALESCE(EXCLUDED.created_at, wallet_targets.created_at),
                total_traded_markets = COALESCE(EXCLUDED.total_traded_markets, wallet_targets.total_traded_markets),
                source_profile_json = EXCLUDED.source_profile_json,
                resolved_at = NOW()
            """,
            (
                target["proxy_wallet"],
                target.get("profile_name"),
                target.get("pseudonym"),
                target.get("bio"),
                target.get("display_username_public"),
                target.get("created_at"),
                target.get("total_traded_markets"),
                Json(target.get("source_profile_json") or {}),
            ),
        )
    conn.commit()


def _bulk_upsert_json_rows(
    conn,
    *,
    table: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
    conflict_target: str,
    update_columns: list[str] | None = None,
    commit: bool = True,
) -> None:
    if not rows:
        return
    update_columns = update_columns or []
    assignments = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_columns)
    conflict_sql = "DO NOTHING" if not assignments else f"DO UPDATE SET {assignments}"
    template = "(" + ", ".join(["%s"] * len(columns)) + ")"
    sql = f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES %s
        ON CONFLICT ({conflict_target}) {conflict_sql}
    """
    with conn.cursor() as cursor:
        execute_values(cursor, sql, rows, template=template, page_size=500)
    if commit:
        conn.commit()


def store_trade_rows(conn, proxy_wallet: str, rows: list[dict[str, Any]]) -> None:
    payload_rows = [
        (
            row_hash({"proxy_wallet": proxy_wallet, "row": row}),
            proxy_wallet,
            row.get("transactionHash"),
            int(row.get("timestamp") or 0),
            row.get("conditionId"),
            row.get("asset"),
            row.get("side"),
            row.get("outcome"),
            row.get("outcomeIndex"),
            row.get("size"),
            row.get("price"),
            row.get("eventSlug"),
            row.get("slug"),
            row.get("title"),
            Json(row),
        )
        for row in rows
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_trades_raw",
        columns=[
            "record_hash",
            "proxy_wallet",
            "transaction_hash",
            "timestamp",
            "condition_id",
            "asset",
            "side",
            "outcome",
            "outcome_index",
            "size",
            "price",
            "event_slug",
            "market_slug",
            "title",
            "payload_json",
        ],
        rows=payload_rows,
        conflict_target="record_hash",
    )


def store_activity_rows(conn, proxy_wallet: str, rows: list[dict[str, Any]]) -> None:
    payload_rows = [
        (
            row_hash({"proxy_wallet": proxy_wallet, "row": row}),
            proxy_wallet,
            row.get("transactionHash"),
            int(row.get("timestamp") or 0),
            row.get("conditionId"),
            row.get("type"),
            row.get("asset"),
            row.get("side"),
            row.get("outcome"),
            row.get("outcomeIndex"),
            row.get("size"),
            row.get("usdcSize"),
            row.get("price"),
            row.get("eventSlug"),
            row.get("slug"),
            row.get("title"),
            Json(row),
        )
        for row in rows
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_activity_raw",
        columns=[
            "record_hash",
            "proxy_wallet",
            "transaction_hash",
            "timestamp",
            "condition_id",
            "event_type",
            "asset",
            "side",
            "outcome",
            "outcome_index",
            "size",
            "usdc_size",
            "price",
            "event_slug",
            "market_slug",
            "title",
            "payload_json",
        ],
        rows=payload_rows,
        conflict_target="record_hash",
    )


def store_positions_rows(conn, proxy_wallet: str, rows: list[dict[str, Any]]) -> None:
    payload_rows = [
        (
            row_hash({"proxy_wallet": proxy_wallet, "row": row}),
            proxy_wallet,
            row.get("conditionId"),
            row.get("asset"),
            row.get("outcome"),
            row.get("size"),
            row.get("avgPrice"),
            row.get("curPrice"),
            row.get("cashPnl"),
            row.get("realizedPnl"),
            row.get("eventSlug"),
            row.get("slug"),
            row.get("title"),
            Json(row),
        )
        for row in rows
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_positions_raw",
        columns=[
            "record_hash",
            "proxy_wallet",
            "condition_id",
            "asset",
            "outcome",
            "size",
            "avg_price",
            "cur_price",
            "cash_pnl",
            "realized_pnl",
            "event_slug",
            "market_slug",
            "title",
            "payload_json",
        ],
        rows=payload_rows,
        conflict_target="record_hash",
    )


def store_closed_positions_rows(conn, proxy_wallet: str, rows: list[dict[str, Any]]) -> None:
    payload_rows = [
        (
            row_hash({"proxy_wallet": proxy_wallet, "row": row}),
            proxy_wallet,
            row.get("conditionId"),
            row.get("asset"),
            row.get("outcome"),
            row.get("totalBought"),
            row.get("avgPrice"),
            row.get("realizedPnl"),
            row.get("eventSlug"),
            row.get("slug"),
            row.get("title"),
            Json(row),
        )
        for row in rows
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_closed_positions_raw",
        columns=[
            "record_hash",
            "proxy_wallet",
            "condition_id",
            "asset",
            "outcome",
            "total_bought",
            "avg_price",
            "realized_pnl",
            "event_slug",
            "market_slug",
            "title",
            "payload_json",
        ],
        rows=payload_rows,
        conflict_target="record_hash",
    )


def store_value_snapshot(conn, proxy_wallet: str, payload: Any) -> None:
    snapshot_id = row_hash(
        {"proxy_wallet": proxy_wallet, "payload": payload, "captured_at": datetime.utcnow().isoformat()}
    )
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO wallet_value_snapshots (snapshot_id, proxy_wallet, payload_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (snapshot_id) DO NOTHING
            """,
            (snapshot_id, proxy_wallet, Json(payload)),
        )
    conn.commit()


def store_tx_receipts(conn, proxy_wallet: str, summaries: list[dict[str, Any]]) -> None:
    deduped: dict[str, dict[str, Any]] = {}
    for item in summaries:
        tx_hash = str(item.get("transaction_hash") or "").strip()
        if not tx_hash:
            continue
        normalized = dict(item)
        normalized["transaction_hash"] = tx_hash
        deduped[tx_hash] = normalized

    rows = [
        (
            item["transaction_hash"],
            proxy_wallet,
            item.get("block_number"),
            item.get("block_timestamp"),
            Json(item.get("classifications") or []),
            Json(item.get("touched_contracts") or []),
            item.get("usdc_in") or 0,
            item.get("usdc_out") or 0,
            Json(item.get("payload_json") or {}),
        )
        for item in deduped.values()
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_tx_receipts",
        columns=[
            "transaction_hash",
            "proxy_wallet",
            "block_number",
            "block_timestamp",
            "classifications_json",
            "touched_contracts_json",
            "usdc_in",
            "usdc_out",
            "payload_json",
        ],
        rows=rows,
        conflict_target="transaction_hash",
        update_columns=[
            "proxy_wallet",
            "block_number",
            "block_timestamp",
            "classifications_json",
            "touched_contracts_json",
            "usdc_in",
            "usdc_out",
            "payload_json",
        ],
    )


def store_market_context_rows(conn, proxy_wallet: str, rows: list[dict[str, Any]]) -> None:
    values = [
        (
            row["market_id"],
            proxy_wallet,
            row.get("event_id"),
            row.get("event_slug"),
            row.get("gamma_market_id"),
            row.get("market_slug"),
            row.get("question"),
            row.get("title"),
            row.get("category"),
            row.get("end_date"),
            row.get("active"),
            row.get("closed"),
            row.get("neg_risk"),
            row.get("resolution_source_url"),
            row.get("yes_token_id"),
            row.get("no_token_id"),
            row.get("yes_price"),
            row.get("no_price"),
            Json(row.get("outcomes") or []),
            Json(row.get("outcome_prices") or []),
            Json(row.get("sibling_market_ids") or []),
            Json(row.get("payload_json") or {}),
        )
        for row in rows
    ]
    _bulk_upsert_json_rows(
        conn,
        table="wallet_market_context",
        columns=[
            "market_id",
            "proxy_wallet",
            "event_id",
            "event_slug",
            "gamma_market_id",
            "market_slug",
            "question",
            "title",
            "category",
            "end_date",
            "active",
            "closed",
            "neg_risk",
            "resolution_source_url",
            "yes_token_id",
            "no_token_id",
            "yes_price",
            "no_price",
            "outcomes_json",
            "outcome_prices_json",
            "sibling_market_ids_json",
            "payload_json",
        ],
        rows=values,
        conflict_target="market_id",
        update_columns=[
            "proxy_wallet",
            "event_id",
            "event_slug",
            "gamma_market_id",
            "market_slug",
            "question",
            "title",
            "category",
            "end_date",
            "active",
            "closed",
            "neg_risk",
            "resolution_source_url",
            "yes_token_id",
            "no_token_id",
            "yes_price",
            "no_price",
            "outcomes_json",
            "outcome_prices_json",
            "sibling_market_ids_json",
            "payload_json",
        ],
    )


def replace_derived_rows(conn, proxy_wallet: str, *, table: str, columns: list[str], rows: list[tuple[Any, ...]]) -> None:
    with conn.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE proxy_wallet = %s", (proxy_wallet,))
    if not rows:
        conn.commit()
        return
    _bulk_upsert_json_rows(
        conn,
        table=table,
        columns=columns,
        rows=rows,
        conflict_target=columns[0],
        update_columns=columns[1:],
        commit=False,
    )
    conn.commit()


def load_rows(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())
