"""CLI and orchestration for wallet-forensics analysis."""

from __future__ import annotations

import argparse
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import httpx
from psycopg2.extras import Json

from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import (
    load_rows,
    replace_derived_rows,
    store_activity_rows,
    store_closed_positions_rows,
    store_market_context_rows,
    store_positions_rows,
    store_trade_rows,
    store_tx_receipts,
    store_value_snapshot,
    upsert_wallet_target,
)
from analysis.wallet_forensics.decoder import decode_receipt_for_wallet
from analysis.wallet_forensics.fetchers import WalletForensicsClient, normalize_event_context
from analysis.wallet_forensics.inference import build_shadow_replay, infer_strategies
from analysis.wallet_forensics.ledger import build_wallet_ledger
from analysis.wallet_forensics.playbooks import build_strategy_blueprints, extract_playbook_sequences
from analysis.wallet_forensics.report import (
    build_markdown_report,
    build_rule_summary,
    build_rule_summary_markdown,
    build_strategy_blueprint_markdown,
    export_artifacts,
)
from analysis.wallet_forensics.schema import ensure_schema
from analysis.wallet_forensics.state import (
    backfill_state_path,
    event_context_pending,
    finalize_backfill_state,
    load_or_create_backfill_state,
    mark_event_context_completed,
    mark_market_stage,
    mark_stage_completed,
    market_stage_pending,
    pending_markets,
    save_backfill_state,
    summarize_backfill_state,
    sync_market_universe,
    update_receipt_progress,
)
from analysis.wallet_forensics.utils import ensure_dir, parse_iso_datetime, safe_int, utc_now
from analysis.wallet_forensics.weather_enrichment import enrich_ledger_with_weather

logger = logging.getLogger(__name__)
RECEIPT_RPC_BATCH_SIZE = 100


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wallet-forensics analysis for public Polymarket histories")
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--profile", type=str, help="Polymarket profile name, for example ColdMath")
    identity_group.add_argument("--wallet", type=str, help="Proxy wallet address to analyze")
    parser.add_argument("--start", type=str, default=None, help="Inclusive UTC start time (ISO-8601)")
    parser.add_argument("--end", type=str, default=None, help="Inclusive UTC end time (ISO-8601)")
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument("--weather-only", action="store_true", help="Filter report/export artifacts to weather markets")
    scope_group.add_argument("--all-markets", action="store_true", help="Report/export all markets")
    parser.add_argument("--output-dir", type=str, default=None, help="Artifact output directory")
    parser.add_argument("--skip-backfill", action="store_true", help="Reuse previously backfilled rows from Postgres")
    parser.add_argument("--skip-report", action="store_true", help="Skip Markdown/CSV/Parquet export")
    parser.add_argument("--skip-parquet", action="store_true", help="Skip Parquet export and only write CSV/JSON/Markdown")
    parser.add_argument("--reset-backfill", action="store_true", help="Reset resumable backfill state before fetching again")
    parser.add_argument("--market-limit", type=int, default=None, help="Optional max markets to process in this run before stopping cleanly")
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_wallet_forensics(args)
    logger.info(
        "Wallet-forensics complete for %s with %d ledger events",
        result["target"]["proxy_wallet"],
        result["completeness"].get("ledger_event_count", 0),
    )
    return 0


def run_wallet_forensics(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    client = WalletForensicsClient()
    conn = get_connection()
    try:
        ensure_schema(conn)
        target = _resolve_target(client, args)
        start_ts, end_ts = _compute_time_bounds(target, args.start, args.end)
        open_ended_scope = args.end is None
        output_dir = _resolve_output_dir(args, target)
        state_path = backfill_state_path(
            output_dir,
            proxy_wallet=target["proxy_wallet"],
            start_ts=start_ts,
            end_ts=None if open_ended_scope else end_ts,
        )

        completeness: dict[str, Any] = {}
        if not args.skip_backfill:
            completeness = _history_backfill(
                conn=conn,
                client=client,
                target=target,
                start_ts=start_ts,
                end_ts=end_ts,
                state_path=state_path,
                open_ended_scope=open_ended_scope,
                reset_backfill=bool(args.reset_backfill),
                market_limit=args.market_limit,
            )

        raw_state = _load_wallet_state(
            conn,
            proxy_wallet=target["proxy_wallet"],
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if not raw_state["activity_rows"]:
            raise RuntimeError(f"No wallet activity found for {target['proxy_wallet']}")

        market_context = _market_context_by_condition(raw_state["market_context_rows"])
        receipt_rows = _receipt_map(raw_state["receipt_rows"])
        ledger_rows, position_snapshots = build_wallet_ledger(
            proxy_wallet=target["proxy_wallet"],
            activity_rows=raw_state["activity_rows"],
            receipt_rows=receipt_rows,
            market_context=market_context,
            closed_positions_rows=raw_state["closed_positions_rows"],
            snapshot_mode="final",
        )

        weather_inputs = _load_weather_inputs(
            conn,
            condition_ids={str(row.get("condition_id") or "") for row in ledger_rows if row.get("condition_id")},
        )
        enriched_rows = enrich_ledger_with_weather(
            ledger_rows=ledger_rows,
            market_context=market_context,
            weather_market_rows=weather_inputs["weather_market_rows"],
            forecast_rows_by_market=weather_inputs["forecast_rows_by_market"],
            observations_by_station=weather_inputs["observations_by_station"],
        )
        inferred_rules = infer_strategies(
            proxy_wallet=target["proxy_wallet"],
            ledger_rows=ledger_rows,
            enriched_rows=enriched_rows,
            market_context=market_context,
        )
        shadow_rows = build_shadow_replay(
            proxy_wallet=target["proxy_wallet"],
            inferred_rules=inferred_rules,
            ledger_rows=enriched_rows,
            market_context=market_context,
        )
        playbook_sequences = extract_playbook_sequences(
            proxy_wallet=target["proxy_wallet"],
            ledger_rows=enriched_rows,
            inferred_rules=inferred_rules,
            market_context=market_context,
        )
        strategy_blueprints = build_strategy_blueprints(
            proxy_wallet=target["proxy_wallet"],
            playbook_sequences=playbook_sequences,
        )
        rule_summary = build_rule_summary(
            target=target,
            ledger_rows=enriched_rows,
            inferred_rules=inferred_rules,
            shadow_rows=shadow_rows,
            strategy_blueprints=strategy_blueprints,
        )

        logger.info(
            "Rebuilt %d ledger events, %d position snapshots, %d inferred rules, %d playbook sequences, %d strategy blueprints, and %d shadow trades for %s",
            len(ledger_rows),
            len(position_snapshots),
            len(inferred_rules),
            len(playbook_sequences),
            len(strategy_blueprints),
            len(shadow_rows),
            target["proxy_wallet"],
        )
        if _should_persist_derived_rows(completeness=completeness):
            logger.info("Persisting derived wallet-forensics tables for %s", target["proxy_wallet"])
            _persist_derived_rows(
                conn=conn,
                proxy_wallet=target["proxy_wallet"],
                ledger_rows=ledger_rows,
                position_snapshots=position_snapshots,
                inferred_rules=inferred_rules,
                playbook_sequences=playbook_sequences,
                strategy_blueprints=strategy_blueprints,
                shadow_rows=shadow_rows,
            )
        else:
            logger.info(
                "Skipping derived-table persistence for %s because the backfill is incomplete; local artifacts still reflect the current partial rebuild",
                target["proxy_wallet"],
            )

        if not completeness:
            completeness = _build_completeness_from_loaded_state(
                raw_state=raw_state,
                ledger_rows=ledger_rows,
                market_context=market_context,
            )
        completeness["ledger_event_count"] = len(ledger_rows)
        completeness["position_snapshot_count"] = len(position_snapshots)
        completeness["inferred_rule_count"] = len(inferred_rules)
        completeness["playbook_sequence_count"] = len(playbook_sequences)
        completeness["strategy_blueprint_count"] = len(strategy_blueprints)
        completeness["shadow_trade_count"] = len(shadow_rows)
        completeness["rule_summary_strategy_count"] = len(rule_summary.get("strategies") or [])

        export_rows, export_rules, export_sequences, export_blueprints, export_shadow = _filter_export_scope(
            weather_only=bool(args.weather_only and not args.all_markets),
            ledger_rows=enriched_rows,
            inferred_rules=inferred_rules,
            playbook_sequences=playbook_sequences,
            strategy_blueprints=strategy_blueprints,
            shadow_rows=shadow_rows,
        )

        report_path = None
        rule_summary_path = None
        rule_summary_markdown_path = None
        strategy_blueprint_path = None
        if not args.skip_report:
            export_artifacts(
                output_dir=output_dir,
                ledger_rows=export_rows,
                inferred_rules=export_rules,
                playbook_sequences=export_sequences,
                strategy_blueprints=export_blueprints,
                shadow_rows=export_shadow,
                rule_summary=rule_summary,
                export_parquet=not bool(args.skip_parquet),
            )
            report_text = build_markdown_report(
                target=target,
                ledger_rows=export_rows,
                inferred_rules=export_rules,
                shadow_rows=export_shadow,
                strategy_blueprints=export_blueprints,
                completeness=completeness,
                scope_label="weather_only" if args.weather_only and not args.all_markets else "all_markets",
            )
            report_path = output_dir / "wallet_forensics_report.md"
            report_path.write_text(report_text, encoding="utf-8")
            rule_summary_markdown_path = output_dir / "wallet_rule_summary.md"
            rule_summary_markdown_path.write_text(
                build_rule_summary_markdown(target=target, rule_summary=rule_summary),
                encoding="utf-8",
            )
            strategy_blueprint_path = output_dir / "wallet_strategy_blueprints.md"
            strategy_blueprint_path.write_text(
                build_strategy_blueprint_markdown(
                    target=target,
                    strategy_blueprints=export_blueprints,
                ),
                encoding="utf-8",
            )
            rule_summary_path = output_dir / "wallet_rule_summary.json"

        return {
            "target": target,
            "completeness": completeness,
            "output_dir": str(output_dir),
            "report_path": str(report_path) if report_path else None,
            "rule_summary_path": str(rule_summary_path) if rule_summary_path else None,
            "rule_summary_markdown_path": str(rule_summary_markdown_path) if rule_summary_markdown_path else None,
            "strategy_blueprint_path": str(strategy_blueprint_path) if strategy_blueprint_path else None,
            "backfill_state_path": str(state_path),
        }
    finally:
        client.close()
        conn.close()


def _resolve_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    search_result: dict[str, Any] | None = None
    if args.profile:
        search_result = client.resolve_wallet(args.profile)
        wallet = _extract_wallet(search_result)
        if not wallet:
            raise RuntimeError(f"Could not resolve a proxy wallet for profile {args.profile!r}")
    else:
        wallet = str(args.wallet or "").strip().lower()
        if not wallet:
            raise RuntimeError("Wallet address is required")

    profile_payload: dict[str, Any] = {}
    try:
        profile_payload = client.fetch_public_profile(wallet)
    except httpx.HTTPError:
        logger.warning("Public profile lookup failed for %s; continuing with limited metadata", wallet)

    total_traded_markets = None
    try:
        total_traded_markets = client.fetch_traded_count(wallet)
    except httpx.HTTPError:
        logger.warning("Traded count lookup failed for %s", wallet)

    created_at = (
        parse_iso_datetime(profile_payload.get("createdAt"))
        or parse_iso_datetime((search_result or {}).get("createdAt"))
        or utc_now()
    )
    return {
        "proxy_wallet": wallet,
        "profile_name": profile_payload.get("name") or (search_result or {}).get("name") or args.profile,
        "pseudonym": profile_payload.get("pseudonym"),
        "bio": profile_payload.get("bio"),
        "display_username_public": profile_payload.get("displayUsernamePublic"),
        "created_at": created_at,
        "total_traded_markets": total_traded_markets,
        "source_profile_json": {
            "search_result": search_result,
            "public_profile": profile_payload,
        },
    }


def _extract_wallet(payload: dict[str, Any]) -> str | None:
    for key in ("proxyWallet", "proxy_wallet", "walletAddress", "wallet", "address"):
        value = payload.get(key)
        if value:
            return str(value).strip().lower()
    return None


def _compute_time_bounds(target: dict[str, Any], start: str | None, end: str | None) -> tuple[int, int]:
    created_at = target.get("created_at")
    start_dt = parse_iso_datetime(start) if start else created_at
    end_dt = parse_iso_datetime(end) if end else utc_now()
    if start_dt is None:
        raise RuntimeError("Could not parse start time")
    if end_dt is None:
        raise RuntimeError("Could not parse end time")
    if end_dt < start_dt:
        raise RuntimeError("End time must be greater than or equal to start time")
    return int(start_dt.timestamp()), int(end_dt.timestamp())


def _history_backfill(
    *,
    conn,
    client: WalletForensicsClient,
    target: dict[str, Any],
    start_ts: int,
    end_ts: int,
    state_path: Path,
    open_ended_scope: bool,
    reset_backfill: bool,
    market_limit: int | None,
) -> dict[str, Any]:
    proxy_wallet = target["proxy_wallet"]
    upsert_wallet_target(conn, target)
    state = load_or_create_backfill_state(
        state_path,
        target=target,
        start_ts=start_ts,
        end_ts=end_ts,
        open_ended=open_ended_scope,
        reset=reset_backfill,
    )

    positions_rows: list[dict[str, Any]]
    closed_positions_rows: list[dict[str, Any]]

    if open_ended_scope or not state["stages"]["value_snapshot"].get("completed"):
        value_snapshot = client.fetch_value_snapshot(proxy_wallet)
        store_value_snapshot(conn, proxy_wallet, value_snapshot)
        mark_stage_completed(state, "value_snapshot")
        save_backfill_state(state_path, state)

    if open_ended_scope or not state["stages"]["positions"].get("completed"):
        positions_rows = client.fetch_positions(proxy_wallet, closed=False)
        store_positions_rows(conn, proxy_wallet, positions_rows)
        mark_stage_completed(state, "positions", row_count=len(positions_rows))
        save_backfill_state(state_path, state)
    else:
        positions_rows = _load_positions_snapshot_rows(conn, proxy_wallet=proxy_wallet, closed=False)

    if open_ended_scope or not state["stages"]["closed_positions"].get("completed"):
        closed_positions_rows = client.fetch_positions(proxy_wallet, closed=True)
        store_closed_positions_rows(conn, proxy_wallet, closed_positions_rows)
        mark_stage_completed(state, "closed_positions", row_count=len(closed_positions_rows))
        save_backfill_state(state_path, state)
    else:
        closed_positions_rows = _load_positions_snapshot_rows(conn, proxy_wallet=proxy_wallet, closed=True)

    known_market_ids = _extract_market_ids([*positions_rows, *closed_positions_rows])
    sync_market_universe(state, known_market_ids)
    save_backfill_state(state_path, state)

    markets_processed_this_run = 0
    for market_id in state.get("market_universe") or []:
        if market_limit is not None and markets_processed_this_run >= market_limit:
            break
        market_work_done = False
        if market_stage_pending(state, market_id, stage_name="activity"):
            market_rows = _filter_rows_by_timestamp(
                client.fetch_activity(
                    proxy_wallet,
                    markets=[market_id],
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                start_ts=start_ts,
                end_ts=end_ts,
            )
            store_activity_rows(conn, proxy_wallet, market_rows)
            mark_market_stage(
                state,
                market_id,
                stage_name="activity",
                row_count=len(market_rows),
                event_slugs=_extract_event_slugs(market_rows),
            )
            save_backfill_state(state_path, state)
            market_work_done = True
        if market_stage_pending(state, market_id, stage_name="trade"):
            market_rows = _filter_rows_by_timestamp(
                client.fetch_trades(
                    proxy_wallet,
                    markets=[market_id],
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
                start_ts=start_ts,
                end_ts=end_ts,
            )
            store_trade_rows(conn, proxy_wallet, market_rows)
            mark_market_stage(
                state,
                market_id,
                stage_name="trade",
                row_count=len(market_rows),
                event_slugs=_extract_event_slugs(market_rows),
            )
            save_backfill_state(state_path, state)
            market_work_done = True
        if market_work_done:
            markets_processed_this_run += 1

    activity_rows = _load_activity_rows(conn, proxy_wallet=proxy_wallet, start_ts=start_ts, end_ts=end_ts)
    trade_rows = _load_trade_rows(conn, proxy_wallet=proxy_wallet, start_ts=start_ts, end_ts=end_ts)

    event_slug_to_markets: dict[str, set[str]] = defaultdict(set)
    for market_id, market_state in (state.get("markets") or {}).items():
        for event_slug in market_state.get("event_slugs") or []:
            if event_slug:
                event_slug_to_markets[event_slug].add(market_id)

    market_context_rows: list[dict[str, Any]] = []
    for event_slug in sorted(event_slug_to_markets):
        if not event_context_pending(state, event_slug):
            continue
        event_payload = client.fetch_event_by_slug(event_slug)
        if not event_payload:
            continue
        normalized_rows = normalize_event_context(event_payload)
        market_context_rows.extend(normalized_rows)
        store_market_context_rows(conn, proxy_wallet, normalized_rows)
        mark_event_context_completed(
            state,
            event_slug,
            market_ids=list(event_slug_to_markets[event_slug]),
        )
        save_backfill_state(state_path, state)

    if pending_markets(state, stage_name="activity"):
        state["stages"]["activity"]["completed"] = False
    else:
        mark_stage_completed(state, "activity", row_count=len(activity_rows))
    if pending_markets(state, stage_name="trade"):
        state["stages"]["trades"]["completed"] = False
    else:
        mark_stage_completed(state, "trades", row_count=len(trade_rows))

    all_event_done = not any(event_context_pending(state, slug) for slug in event_slug_to_markets)
    if all_event_done:
        mark_stage_completed(state, "market_context", event_count=len(event_slug_to_markets))

    activity_types_by_tx: dict[str, set[str]] = defaultdict(set)
    tx_hashes: set[str] = set()
    for row in activity_rows:
        tx_hash = str(row.get("transaction_hash") or row.get("transactionHash") or "").strip()
        if not tx_hash:
            continue
        tx_hashes.add(tx_hash)
        activity_type = str(row.get("event_type") or row.get("type") or "").strip()
        if activity_type:
            activity_types_by_tx[tx_hash].add(activity_type)
    for row in trade_rows:
        tx_hash = str(row.get("transaction_hash") or row.get("transactionHash") or "").strip()
        if tx_hash:
            tx_hashes.add(tx_hash)

    existing_receipt_hashes = _load_existing_receipt_hashes(conn, proxy_wallet=proxy_wallet)
    pending_receipts = [tx_hash for tx_hash in sorted(tx_hashes) if tx_hash not in existing_receipt_hashes]
    receipt_summaries_batch: list[dict[str, Any]] = []
    completed_receipt_count = len(existing_receipt_hashes)
    for batch_start in range(0, len(pending_receipts), RECEIPT_RPC_BATCH_SIZE):
        tx_batch = pending_receipts[batch_start: batch_start + RECEIPT_RPC_BATCH_SIZE]
        receipt_payloads = client.fetch_transaction_receipts(tx_batch)
        for tx_hash in tx_batch:
            summary = decode_receipt_for_wallet(
                receipt_payloads.get(tx_hash),
                proxy_wallet,
                activity_types=sorted(activity_types_by_tx.get(tx_hash, ())),
            )
            if not summary.get("transaction_hash"):
                summary["transaction_hash"] = tx_hash
            receipt_summaries_batch.append(summary)
            completed_receipt_count += 1
        store_tx_receipts(conn, proxy_wallet, receipt_summaries_batch)
        receipt_summaries_batch.clear()
        update_receipt_progress(
            state,
            completed_count=completed_receipt_count,
            pending_count=max(0, len(pending_receipts) - (completed_receipt_count - len(existing_receipt_hashes))),
            last_transaction_hash=tx_batch[-1] if tx_batch else None,
        )
        save_backfill_state(state_path, state)
    if receipt_summaries_batch:
        store_tx_receipts(conn, proxy_wallet, receipt_summaries_batch)
    update_receipt_progress(
        state,
        completed_count=completed_receipt_count,
        pending_count=0,
        last_transaction_hash=pending_receipts[-1] if pending_receipts else None,
        completed=True,
    )

    finalize_backfill_state(state)
    save_backfill_state(state_path, state)

    completeness = {
        "trade_count": len(trade_rows),
        "activity_count": len(activity_rows),
        "position_count": len(positions_rows),
        "closed_position_count": len(closed_positions_rows),
        "receipt_count": len(tx_hashes),
        "market_context_count": len(event_slug_to_markets),
        "backfill_state_path": str(state_path),
        "resume_required": not bool(state.get("complete")),
        "markets_processed_this_run": markets_processed_this_run,
    }
    completeness.update(summarize_backfill_state(state))
    return completeness


def _load_wallet_state(
    conn,
    *,
    proxy_wallet: str,
    start_ts: int,
    end_ts: int,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "trade_rows": _load_trade_rows(conn, proxy_wallet=proxy_wallet, start_ts=start_ts, end_ts=end_ts),
        "activity_rows": _load_activity_rows(conn, proxy_wallet=proxy_wallet, start_ts=start_ts, end_ts=end_ts),
        "positions_rows": _load_positions_snapshot_rows(conn, proxy_wallet=proxy_wallet, closed=False),
        "closed_positions_rows": _load_positions_snapshot_rows(conn, proxy_wallet=proxy_wallet, closed=True),
        "receipt_rows": load_rows(
            conn,
            """
            SELECT
                transaction_hash,
                proxy_wallet,
                block_number,
                block_timestamp,
                classifications_json,
                touched_contracts_json,
                usdc_in,
                usdc_out
            FROM wallet_tx_receipts
            WHERE proxy_wallet = %s
            """,
            (proxy_wallet,),
        ),
        "market_context_rows": load_rows(
            conn,
            """
            SELECT
                market_id,
                proxy_wallet,
                event_id,
                event_slug,
                gamma_market_id,
                market_slug,
                question,
                title,
                category,
                end_date,
                active,
                closed,
                neg_risk,
                resolution_source_url,
                yes_token_id,
                no_token_id,
                yes_price,
                no_price,
                outcomes_json,
                outcome_prices_json,
                sibling_market_ids_json,
                payload_json
            FROM wallet_market_context
            WHERE proxy_wallet = %s
            """,
            (proxy_wallet,),
        ),
    }


def _load_activity_rows(conn, *, proxy_wallet: str, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    return load_rows(
        conn,
        """
        SELECT
            record_hash,
            proxy_wallet,
            transaction_hash,
            timestamp,
            condition_id,
            event_type,
            asset,
            side,
            outcome,
            outcome_index,
            size,
            usdc_size,
            price,
            event_slug,
            market_slug,
            title
        FROM wallet_activity_raw
        WHERE proxy_wallet = %s
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC, transaction_hash ASC
        """,
        (proxy_wallet, start_ts, end_ts),
    )


def _load_trade_rows(conn, *, proxy_wallet: str, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    return load_rows(
        conn,
        """
        SELECT
            record_hash,
            proxy_wallet,
            transaction_hash,
            timestamp,
            condition_id,
            asset,
            side,
            outcome,
            outcome_index,
            size,
            price,
            event_slug,
            market_slug,
            title
        FROM wallet_trades_raw
        WHERE proxy_wallet = %s
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC, transaction_hash ASC
        """,
        (proxy_wallet, start_ts, end_ts),
    )


def _load_positions_snapshot_rows(conn, *, proxy_wallet: str, closed: bool) -> list[dict[str, Any]]:
    if closed:
        return load_rows(
            conn,
            """
            SELECT
                record_hash,
                proxy_wallet,
                condition_id,
                asset,
                outcome,
                total_bought,
                avg_price,
                realized_pnl,
                event_slug,
                market_slug,
                title
            FROM wallet_closed_positions_raw
            WHERE proxy_wallet = %s
            """,
            (proxy_wallet,),
        )
    return load_rows(
        conn,
        """
        SELECT
            record_hash,
            proxy_wallet,
            condition_id,
            asset,
            outcome,
            size,
            avg_price,
            cur_price,
            cash_pnl,
            realized_pnl,
            event_slug,
            market_slug,
            title
        FROM wallet_positions_raw
        WHERE proxy_wallet = %s
        """,
        (proxy_wallet,),
    )


def _load_existing_receipt_hashes(conn, *, proxy_wallet: str) -> set[str]:
    rows = load_rows(
        conn,
        """
        SELECT transaction_hash
        FROM wallet_tx_receipts
        WHERE proxy_wallet = %s
        """,
        (proxy_wallet,),
    )
    return {str(row.get("transaction_hash") or "").strip() for row in rows if str(row.get("transaction_hash") or "").strip()}


def _extract_market_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(row.get("conditionId") or row.get("condition_id") or "").strip()
            for row in rows
            if str(row.get("conditionId") or row.get("condition_id") or "").strip()
        }
    )


def _extract_event_slugs(rows: Iterable[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(row.get("eventSlug") or row.get("event_slug") or "").strip()
            for row in rows
            if str(row.get("eventSlug") or row.get("event_slug") or "").strip()
        }
    )


def _receipt_map(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        tx_hash = str(row.get("transaction_hash") or "").strip()
        if not tx_hash:
            continue
        result[tx_hash] = {
            "transaction_hash": tx_hash,
            "block_number": row.get("block_number"),
            "block_timestamp": row.get("block_timestamp"),
            "classifications": row.get("classifications_json") or [],
            "touched_contracts": row.get("touched_contracts_json") or [],
            "usdc_in": row.get("usdc_in"),
            "usdc_out": row.get("usdc_out"),
        }
    return result


def _market_context_by_condition(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        market_id = str(row.get("market_id") or "").strip()
        if not market_id:
            continue
        result[market_id] = {
            "market_id": market_id,
            "event_id": row.get("event_id"),
            "event_slug": row.get("event_slug"),
            "gamma_market_id": row.get("gamma_market_id"),
            "market_slug": row.get("market_slug"),
            "question": row.get("question"),
            "title": row.get("title"),
            "category": row.get("category"),
            "end_date": row.get("end_date"),
            "active": row.get("active"),
            "closed": row.get("closed"),
            "neg_risk": row.get("neg_risk"),
            "resolution_source_url": row.get("resolution_source_url"),
            "yes_token_id": row.get("yes_token_id"),
            "no_token_id": row.get("no_token_id"),
            "yes_price": row.get("yes_price"),
            "no_price": row.get("no_price"),
            "outcomes": row.get("outcomes_json") or [],
            "outcome_prices": row.get("outcome_prices_json") or [],
            "sibling_market_ids": row.get("sibling_market_ids_json") or [],
            "payload_json": row.get("payload_json") or {},
        }
    return result


def _load_weather_inputs(conn, *, condition_ids: set[str]) -> dict[str, Any]:
    if not condition_ids:
        return {
            "weather_market_rows": {},
            "forecast_rows_by_market": {},
            "observations_by_station": {},
        }

    market_rows = load_rows(
        conn,
        """
        SELECT
            market_id,
            city,
            station_code,
            timezone,
            local_date,
            bucket_label,
            bucket_low,
            bucket_high,
            resolution_precision_scale
        FROM weather_market_catalog
        WHERE market_id = ANY(%s)
        """,
        (list(condition_ids),),
    )
    weather_market_rows = {str(row["market_id"]): row for row in market_rows}
    if not weather_market_rows:
        return {
            "weather_market_rows": {},
            "forecast_rows_by_market": {},
            "observations_by_station": {},
        }

    market_ids = list(weather_market_rows)
    forecast_rows = load_rows(
        conn,
        """
        SELECT
            market_id,
            captured_at,
            provider,
            model,
            run_at,
            forecast_for,
            temp_max,
            temp_hourly,
            cloud,
            wind,
            dewpoint,
            precip_prob,
            payload_json
        FROM weather_forecast_snapshots
        WHERE market_id = ANY(%s)
        ORDER BY market_id ASC, run_at ASC, captured_at ASC
        """,
        (market_ids,),
    )
    forecast_rows_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in forecast_rows:
        forecast_rows_by_market[str(row["market_id"])].append(row)

    station_codes = sorted(
        {
            str(row.get("station_code") or "").strip()
            for row in market_rows
            if str(row.get("station_code") or "").strip()
        }
    )
    observation_rows: list[dict[str, Any]] = []
    if station_codes:
        observation_rows = load_rows(
            conn,
            """
            SELECT
                station_code,
                observed_at,
                temperature,
                dewpoint,
                wind_speed,
                wind_direction,
                wind_gust,
                cloud,
                visibility,
                payload_json
            FROM weather_observations
            WHERE station_code = ANY(%s)
            ORDER BY station_code ASC, observed_at ASC
            """,
            (station_codes,),
        )
    observations_by_station: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observation_rows:
        observations_by_station[str(row["station_code"])].append(row)

    return {
        "weather_market_rows": weather_market_rows,
        "forecast_rows_by_market": dict(forecast_rows_by_market),
        "observations_by_station": dict(observations_by_station),
    }


def _persist_derived_rows(
    *,
    conn,
    proxy_wallet: str,
    ledger_rows: list[dict[str, Any]],
    position_snapshots: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    playbook_sequences: list[dict[str, Any]],
    strategy_blueprints: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
) -> None:
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_ledger_events",
        columns=[
            "ledger_event_id",
            "proxy_wallet",
            "occurred_at",
            "transaction_hash",
            "condition_id",
            "event_slug",
            "asset",
            "outcome",
            "side",
            "event_type",
            "size",
            "token_delta",
            "usdc_delta",
            "price",
            "realized_pnl",
            "source_confidence",
            "source_details_json",
            "payload_json",
        ],
        rows=[
            (
                row["ledger_event_id"],
                row["proxy_wallet"],
                row["occurred_at"],
                row.get("transaction_hash"),
                row.get("condition_id"),
                row.get("event_slug"),
                row.get("asset"),
                row.get("outcome"),
                row.get("side"),
                row.get("event_type"),
                row.get("size"),
                row.get("token_delta"),
                row.get("usdc_delta"),
                row.get("price"),
                row.get("realized_pnl"),
                row.get("source_confidence"),
                Json(row.get("source_details_json") or {}),
                Json(row.get("payload_json") or {}),
            )
            for row in ledger_rows
        ],
    )
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_positions_rebuilt",
        columns=[
            "snapshot_id",
            "proxy_wallet",
            "ledger_event_id",
            "condition_id",
            "asset",
            "outcome",
            "position_size",
            "average_cost",
            "cost_basis",
            "realized_pnl_cumulative",
            "payload_json",
        ],
        rows=[
            (
                row["snapshot_id"],
                row["proxy_wallet"],
                row["ledger_event_id"],
                row.get("condition_id"),
                row.get("asset"),
                row.get("outcome"),
                row.get("position_size"),
                row.get("average_cost"),
                row.get("cost_basis"),
                row.get("realized_pnl_cumulative"),
                Json(row.get("payload_json") or {}),
            )
            for row in position_snapshots
        ],
    )
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_inferred_rules",
        columns=[
            "rule_id",
            "proxy_wallet",
            "strategy_key",
            "scope_type",
            "scope_id",
            "condition_id",
            "asset",
            "confidence",
            "summary",
            "trade_ids_json",
            "evidence_json",
        ],
        rows=[
            (
                row["rule_id"],
                row["proxy_wallet"],
                row["strategy_key"],
                row["scope_type"],
                row["scope_id"],
                row.get("condition_id"),
                row.get("asset"),
                row.get("confidence"),
                row.get("summary"),
                Json(row.get("trade_ids_json") or []),
                Json(row.get("evidence_json") or {}),
            )
            for row in inferred_rules
        ],
    )
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_playbook_sequences",
        columns=[
            "sequence_id",
            "proxy_wallet",
            "strategy_key",
            "strategy_tags_json",
            "scope_type",
            "scope_id",
            "condition_id",
            "event_slug",
            "started_at",
            "ended_at",
            "duration_minutes",
            "trade_count",
            "buy_count",
            "merge_count",
            "redeem_count",
            "distinct_conditions",
            "realized_pnl",
            "confidence",
            "summary",
            "payload_json",
        ],
        rows=[
            (
                row["sequence_id"],
                row["proxy_wallet"],
                row["strategy_key"],
                Json(row.get("strategy_tags_json") or []),
                row["scope_type"],
                row["scope_id"],
                row.get("condition_id"),
                row.get("event_slug"),
                row.get("started_at"),
                row.get("ended_at"),
                row.get("duration_minutes"),
                row.get("trade_count"),
                row.get("buy_count"),
                row.get("merge_count"),
                row.get("redeem_count"),
                row.get("distinct_conditions"),
                row.get("realized_pnl"),
                row.get("confidence"),
                row.get("summary"),
                Json(row.get("payload_json") or {}),
            )
            for row in playbook_sequences
        ],
    )
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_strategy_blueprints",
        columns=[
            "blueprint_id",
            "proxy_wallet",
            "strategy_key",
            "status",
            "confidence",
            "priority_score",
            "support_count",
            "distinct_conditions",
            "distinct_events",
            "realized_pnl_total",
            "realized_pnl_avg",
            "win_rate",
            "summary",
            "entry_rule_json",
            "sizing_rule_json",
            "exit_rule_json",
            "risk_rule_json",
            "evidence_json",
        ],
        rows=[
            (
                row["blueprint_id"],
                row["proxy_wallet"],
                row["strategy_key"],
                row["status"],
                row.get("confidence"),
                row.get("priority_score"),
                row.get("support_count"),
                row.get("distinct_conditions"),
                row.get("distinct_events"),
                row.get("realized_pnl_total"),
                row.get("realized_pnl_avg"),
                row.get("win_rate"),
                row.get("summary"),
                Json(row.get("entry_rule_json") or {}),
                Json(row.get("sizing_rule_json") or {}),
                Json(row.get("exit_rule_json") or {}),
                Json(row.get("risk_rule_json") or {}),
                Json(row.get("evidence_json") or {}),
            )
            for row in strategy_blueprints
        ],
    )
    replace_derived_rows(
        conn,
        proxy_wallet,
        table="wallet_shadow_replay_trades",
        columns=[
            "shadow_trade_id",
            "proxy_wallet",
            "rule_id",
            "condition_id",
            "asset",
            "side",
            "entry_at",
            "entry_price",
            "exit_mark_price",
            "size",
            "resolved",
            "pnl_slippage_free",
            "pnl_conservative",
            "payload_json",
        ],
        rows=[
            (
                row["shadow_trade_id"],
                row["proxy_wallet"],
                row.get("rule_id"),
                row.get("condition_id"),
                row.get("asset"),
                row.get("side"),
                row.get("entry_at"),
                row.get("entry_price"),
                row.get("exit_mark_price"),
                row.get("size"),
                row.get("resolved"),
                row.get("pnl_slippage_free"),
                row.get("pnl_conservative"),
                Json(row.get("payload_json") or {}),
            )
            for row in shadow_rows
        ],
    )


def _build_completeness_from_loaded_state(
    *,
    raw_state: dict[str, list[dict[str, Any]]],
    ledger_rows: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trade_count": len(raw_state["trade_rows"]),
        "activity_count": len(raw_state["activity_rows"]),
        "position_count": len(raw_state["positions_rows"]),
        "closed_position_count": len(raw_state["closed_positions_rows"]),
        "receipt_count": len(raw_state["receipt_rows"]),
        "market_context_count": len(market_context),
        "ledger_event_count": len(ledger_rows),
    }


def _should_persist_derived_rows(*, completeness: dict[str, Any]) -> bool:
    if not completeness:
        return True
    return not bool(completeness.get("resume_required"))


def _filter_export_scope(
    *,
    weather_only: bool,
    ledger_rows: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    playbook_sequences: list[dict[str, Any]],
    strategy_blueprints: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if not weather_only:
        return ledger_rows, inferred_rules, playbook_sequences, strategy_blueprints, shadow_rows

    weather_ledger = [row for row in ledger_rows if row.get("is_weather")]
    weather_conditions = {str(row.get("condition_id") or "") for row in weather_ledger if row.get("condition_id")}
    weather_events = {str(row.get("event_slug") or "") for row in weather_ledger if str(row.get("event_slug") or "")}
    weather_trade_ids = {row["ledger_event_id"] for row in weather_ledger}
    filtered_rules = [
        row
        for row in inferred_rules
        if str(row.get("condition_id") or "") in weather_conditions
        or any(trade_id in weather_trade_ids for trade_id in row.get("trade_ids_json") or [])
    ]
    filtered_sequences = [
        row
        for row in playbook_sequences
        if str(row.get("condition_id") or "") in weather_conditions
        or str(row.get("event_slug") or "") in weather_events
    ]
    strategy_keys = {str(row.get("strategy_key") or "") for row in filtered_sequences if str(row.get("strategy_key") or "")}
    filtered_blueprints = [
        row for row in strategy_blueprints
        if str(row.get("strategy_key") or "") in strategy_keys
    ]
    filtered_shadow = [
        row for row in shadow_rows
        if str(row.get("condition_id") or "") in weather_conditions
    ]
    return weather_ledger, filtered_rules, filtered_sequences, filtered_blueprints, filtered_shadow


def _filter_rows_by_timestamp(
    rows: list[dict[str, Any]],
    *,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if start_ts <= (safe_int(row.get("timestamp")) or 0) <= end_ts
    ]


def _resolve_output_dir(args: argparse.Namespace, target: dict[str, Any]) -> Path:
    if args.output_dir:
        return ensure_dir(Path(args.output_dir).resolve())

    label_source = target.get("profile_name") or target["proxy_wallet"]
    label = _slugify(str(label_source))
    if not label:
        label = target["proxy_wallet"][:10]
    return ensure_dir(_results_root() / label)


def _results_root() -> Path:
    return ensure_dir(Path(__file__).resolve().parents[2] / "results" / "wallet_forensics")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
