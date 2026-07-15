"""ColdMath public-parity replay and deterministic strategy reconstruction."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import json
import logging
from math import floor
from pathlib import Path
from statistics import median
from typing import Any
from datetime import UTC, datetime, timedelta

from analysis.coldmath_quote_parity import (
    _build_context_for_event,
    _counter_rows,
    _load_historical_weather_state,
    _nearest_quote_row,
    _normalize_weather_trades,
)
from analysis.coldmath_window_compare import _extract_wallet
from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.utils import ensure_dir, parse_iso_datetime, safe_float
from trading_weather.clone_config import (
    PAIR_PLAYBOOK_KEYS,
    apply_clone_size_model,
    build_clone_size_model,
    normalize_clone_bot_config,
)
from trading_weather.clone_engine import (
    build_clone_runtime,
    evaluate_clone_cycle,
    plan_directional_entry,
    plan_neg_risk_entry,
    plan_paired_entry,
)
from trading_weather import config as weather_config

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = "ColdMath"
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_OUTPUT_DIR = SRC_ROOT / "results" / "wallet_forensics" / "coldmath_public_parity_48h"
DEFAULT_CLONE_CONFIG_PATH = (
    SRC_ROOT
    / "results"
    / "wallet_forensics"
    / "coldmath_resume_smoke_v3"
    / "wallet_coldmath_clone_bot_config.json"
)
DEFAULT_LOOKBACK_HOURS = 48.0
DEFAULT_QUOTE_WINDOW_SECONDS = 180
DEFAULT_SEQUENCE_GAP_SECONDS = 120
DEFAULT_MATCH_WINDOW_SECONDS = 60.0
TRAIN_SPLIT_RATIO = 0.70

MISS_BUCKETS = {
    "market_not_in_replay_universe",
    "missing_quote_pair",
    "stale_quote",
    "paired_under_par_rejected",
    "neg_risk_basket_rejected",
    "cheap_bucket_rejected",
    "high_prob_rejected",
    "tail_bucket_rejected",
    "inventory_guard_blocked",
    "exposure_or_spend_cap_blocked",
    "order_size_model_mismatch",
    "repeat_entry_rule_mismatch",
    "closeout_rule_mismatch",
    "unsupported_public_behavior",
}

PLAYBOOK_REJECTION_BUCKETS = {
    "paired_under_par": "paired_under_par_rejected",
    "asymmetric_paired_accumulation": "paired_under_par_rejected",
    "neg_risk_basket": "neg_risk_basket_rejected",
    "cheap_bucket_accumulation": "cheap_bucket_rejected",
    "high_prob_bucket_accumulation": "high_prob_rejected",
    "tail_bucket_accumulation": "tail_bucket_rejected",
    "inventory_rebalance_and_exit": "closeout_rule_mismatch",
}


def _is_pair_playbook(playbook_key: str) -> bool:
    return playbook_key in PAIR_PLAYBOOK_KEYS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ColdMath 48h public-parity replay and strategy reconstruction")
    parser.add_argument("--profile", type=str, default=DEFAULT_PROFILE)
    parser.add_argument("--wallet", type=str, default=None)
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--window-start", type=str, default=None, help="Explicit UTC window start (ISO 8601)")
    parser.add_argument("--window-end", type=str, default=None, help="Explicit UTC window end (ISO 8601)")
    parser.add_argument("--quote-window-seconds", type=int, default=DEFAULT_QUOTE_WINDOW_SECONDS)
    parser.add_argument("--sequence-gap-seconds", type=int, default=DEFAULT_SEQUENCE_GAP_SECONDS)
    parser.add_argument("--match-window-seconds", type=float, default=DEFAULT_MATCH_WINDOW_SECONDS)
    parser.add_argument("--clone-config-path", type=str, default=str(DEFAULT_CLONE_CONFIG_PATH))
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_public_parity(args)
    logger.info(
        "ColdMath public parity complete: covered trades=%s replay match rate=%.4f gate=%s",
        result["summary"]["covered_trade_count"],
        result["summary"]["holdout_metrics"]["covered_trade_match_rate_condition_side"],
        result["summary"]["deployment_gate"],
    )
    return 0


def run_public_parity(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    artifact_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ensure_dir(Path(args.output_dir).resolve() / artifact_id)
    clone_config = normalize_clone_bot_config(json.loads(Path(args.clone_config_path).read_text(encoding="utf-8")))
    logger.info("Resolving ColdMath profile and fetching public weather trades")
    client = WalletForensicsClient()
    try:
        wallet_target = _resolve_wallet_target(client, args)
        requested_window = _requested_window(
            lookback_hours=float(args.lookback_hours),
            window_start=args.window_start,
            window_end=args.window_end,
        )
        trade_rows = _fetch_public_weather_trades(
            client,
            wallet=wallet_target["proxy_wallet"],
            window_start=requested_window["requested_start_utc"],
            window_end=requested_window["requested_end_utc"],
        )
    finally:
        client.close()

    if not trade_rows:
        raise RuntimeError("No ColdMath weather trades found in the requested window")

    event_slugs = sorted({str(row.get("event_slug") or "") for row in trade_rows if row.get("event_slug")})
    logger.info("Loaded %s public weather trades across %s event slugs", len(trade_rows), len(event_slugs))
    coverage = _load_quote_coverage(event_slugs=event_slugs)
    try:
        covered_window = _clip_covered_window(
            requested_start=requested_window["requested_start_utc"],
            requested_end=requested_window["requested_end_utc"],
            coverage_start=coverage.get("coverage_start_utc"),
            coverage_end=coverage.get("coverage_end_utc"),
        )
    except RuntimeError:
        coverage_start = coverage.get("coverage_start_utc")
        coverage_end = coverage.get("coverage_end_utc")
        if coverage_start is None or coverage_end is None:
            raise
        logger.warning(
            "Requested window has no overlap with recorded quotes; falling back to recorded coverage %s -> %s",
            coverage_start,
            coverage_end,
        )
        client = WalletForensicsClient()
        try:
            trade_rows = _fetch_public_weather_trades(
                client,
                wallet=wallet_target["proxy_wallet"],
                window_start=coverage_start,
                window_end=coverage_end,
            )
        finally:
            client.close()
        event_slugs = sorted({str(row.get("event_slug") or "") for row in trade_rows if row.get("event_slug")})
        coverage = _load_quote_coverage(event_slugs=event_slugs)
        covered_window = {
            "covered_start_utc": coverage_start,
            "covered_end_utc": coverage_end,
        }
    logger.info(
        "Quote coverage: %s -> %s across %s rows / %s markets",
        coverage.get("coverage_start_utc"),
        coverage.get("coverage_end_utc"),
        coverage.get("quote_row_count"),
        coverage.get("quote_market_count"),
    )
    logger.info("Loading historical weather catalog and quote tape for replay window")
    catalog_by_event, quote_series = _load_historical_weather_state(
        event_slugs=event_slugs,
        window_start=covered_window["covered_start_utc"],
        window_end=covered_window["covered_end_utc"],
    )
    event_bounds = _event_quote_bounds(catalog_by_event=catalog_by_event, quote_series=quote_series)
    grouped_sequences = _group_public_trade_sequences(
        trade_rows,
        gap_seconds=int(args.sequence_gap_seconds),
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
    )
    sequence_playbooks = {
        str(row["sequence_id"]): str(row.get("public_playbook") or "unsupported_public_behavior")
        for row in grouped_sequences
    }
    trade_rows = [
        {
            **row,
            "public_playbook": sequence_playbooks.get(str(row.get("sequence_id") or ""), "unsupported_public_behavior"),
        }
        for row in trade_rows
    ]
    covered_rows, uncovered_rows = _mark_trade_coverage(
        trade_rows,
        covered_start=covered_window["covered_start_utc"],
        covered_end=covered_window["covered_end_utc"],
        catalog_by_event=catalog_by_event,
        event_bounds=event_bounds,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
    )
    clone_config = _prepare_parity_clone_config(clone_config, covered_rows=covered_rows)
    logger.info(
        "Coverage classification complete: %s covered / %s uncovered",
        len(covered_rows),
        len(uncovered_rows),
    )
    training_rows, holdout_rows = _split_training_holdout(covered_rows)

    logger.info(
        "Tuning strategy on %s training trades and %s holdout trades",
        len(training_rows),
        len(holdout_rows),
    )
    tuned = _tune_clone_strategy(
        training_rows=training_rows,
        holdout_rows=holdout_rows,
        base_config=clone_config,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
        match_window_seconds=float(args.match_window_seconds),
    )
    final_config = apply_clone_size_model(tuned["clone_config"], tuned["size_model"])
    logger.info("Evaluating trade-time parity with tuned config")
    trade_time_parity = _evaluate_trade_time_parity(
        trade_rows=covered_rows,
        clone_config=final_config,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
        match_window_seconds=float(args.match_window_seconds),
    )
    logger.info("Running full historical replay")
    replay = _run_full_replay(
        trade_rows=covered_rows,
        clone_config=final_config,
        size_model=tuned["size_model"],
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        event_bounds=event_bounds,
        quote_window_seconds=int(args.quote_window_seconds),
        match_window_seconds=float(args.match_window_seconds),
    )
    miss_rows = _classify_public_parity_misses(
        covered_rows=covered_rows,
        trade_time_rows=trade_time_parity["rows"],
        replay_rows=replay["replay_trades"],
        blocked_rows=replay["blocked_candidates"],
        match_window_seconds=float(args.match_window_seconds),
    )
    overall_metrics = replay["metrics"]
    holdout_metrics = _filter_metrics_to_rows(replay["matched_rows"], holdout_rows)
    holdout_miss_rows = _filter_rows_to_trade_set(miss_rows, holdout_rows)
    gate_result = _deployment_gate_result(
        holdout_metrics=holdout_metrics,
        miss_rows=holdout_miss_rows,
        parity_config=final_config.get("parity") or {},
    )
    approved_clone_config = deepcopy(final_config)
    approved_clone_config.setdefault("deployment", {})
    approved_clone_config["deployment"]["approved_parity_artifact"] = artifact_id if gate_result.get("passed") else None
    approved_clone_config["deployment"]["release_gate_status"] = "approved" if gate_result.get("passed") else "replay_failed"

    artifacts = {
        "coldmath_public_trades_48h.csv": trade_rows,
        "coldmath_public_sequences_48h.csv": grouped_sequences,
        "coldmath_trade_time_parity.csv": trade_time_parity["rows"],
        "coldmath_full_replay_trades.csv": replay["replay_trades"],
        "coldmath_miss_classification.csv": miss_rows,
    }
    for name, rows in artifacts.items():
        _write_csv(output_dir / name, rows)

    inference_payload = {
        "wallet": wallet_target["proxy_wallet"],
        "requested_window": requested_window,
        "covered_window": covered_window,
        "strategy_parameters": tuned["strategy_parameters"],
        "size_model": tuned["size_model"],
        "training_metrics": tuned["training_metrics"],
        "holdout_metrics": tuned["holdout_metrics"],
    }
    summary = {
        "artifact_id": artifact_id,
        "artifact_dir": str(output_dir),
        "requested_window": requested_window,
        "covered_window": covered_window,
        "coldmath_trade_count": len(trade_rows),
        "covered_trade_count": len(covered_rows),
        "uncovered_trade_count": len(uncovered_rows),
        "coverage": coverage,
        "parity_metrics": overall_metrics,
        "trade_time_metrics": trade_time_parity["metrics"],
        "full_replay_metrics": overall_metrics,
        "training_metrics": tuned["training_metrics"],
        "holdout_metrics": holdout_metrics,
        "deployment_gate": gate_result,
        "tuned_strategy_parameters": tuned["strategy_parameters"],
        "approved_clone_config_path": str(output_dir / "coldmath_clone_config_release_candidate.json"),
    }
    logger.info(
        "Parity complete: replay match_rate=%.4f playbook_rate=%.4f gate=%s",
        float(overall_metrics.get("covered_trade_match_rate_condition_side") or 0.0),
        float(overall_metrics.get("covered_trade_match_rate_playbook") or 0.0),
        gate_result.get("passed"),
    )
    (output_dir / "coldmath_strategy_inference.json").write_text(
        json.dumps(inference_payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "coldmath_public_parity_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "coldmath_clone_config_release_candidate.json").write_text(
        json.dumps(approved_clone_config, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "coldmath_public_parity_report.md").write_text(
        _build_markdown_report(
            wallet_target=wallet_target,
            summary=summary,
            uncovered_rows=uncovered_rows,
            grouped_sequences=grouped_sequences,
            miss_rows=miss_rows,
        ),
        encoding="utf-8",
    )
    return {
        "wallet_target": wallet_target,
        "trade_rows": trade_rows,
        "covered_rows": covered_rows,
        "uncovered_rows": uncovered_rows,
        "grouped_sequences": grouped_sequences,
        "trade_time_parity": trade_time_parity,
        "replay": replay,
        "miss_rows": miss_rows,
        "summary": summary,
        "output_dir": str(output_dir),
    }


def _resolve_wallet_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.wallet:
        wallet = str(args.wallet).strip().lower()
    else:
        resolved = client.resolve_wallet(str(args.profile))
        wallet = str(_extract_wallet(resolved) or "").strip().lower()
    if not wallet:
        raise RuntimeError("Could not resolve ColdMath proxy wallet")
    profile_payload: dict[str, Any] = {}
    try:
        profile_payload = client.fetch_public_profile(wallet)
    except Exception:
        logger.warning("Public profile lookup failed for %s", wallet)
    return {
        "proxy_wallet": wallet,
        "profile_name": profile_payload.get("name") or args.profile,
    }


def _requested_window(lookback_hours: float, *, window_start: str | None, window_end: str | None) -> dict[str, Any]:
    if window_start or window_end:
        if not window_start or not window_end:
            raise RuntimeError("Both --window-start and --window-end must be provided together")
        requested_start = parse_iso_datetime(window_start)
        requested_end = parse_iso_datetime(window_end)
        if requested_start is None or requested_end is None:
            raise RuntimeError("Could not parse --window-start/--window-end as ISO datetimes")
        if requested_start.tzinfo is None:
            requested_start = requested_start.replace(tzinfo=UTC)
        else:
            requested_start = requested_start.astimezone(UTC)
        if requested_end.tzinfo is None:
            requested_end = requested_end.replace(tzinfo=UTC)
        else:
            requested_end = requested_end.astimezone(UTC)
        if requested_start > requested_end:
            raise RuntimeError("--window-start must be <= --window-end")
    else:
        requested_end = datetime.now(UTC)
        requested_start = requested_end - timedelta(hours=lookback_hours)
    return {
        "requested_start_utc": requested_start,
        "requested_end_utc": requested_end,
        "requested_lookback_hours": lookback_hours,
    }


def _fetch_public_weather_trades(
    client: WalletForensicsClient,
    *,
    wallet: str,
    window_start,
    window_end,
) -> list[dict[str, Any]]:
    rows = client.fetch_trades(
        wallet,
        start_ts=int(window_start.timestamp()),
        end_ts=int(window_end.timestamp()),
    )
    weather_rows = []
    for row in rows:
        slug = str(row.get("slug") or row.get("eventSlug") or row.get("event_slug") or "").lower()
        title = str(row.get("title") or row.get("question") or "").lower()
        if slug.startswith(("highest-temperature-", "lowest-temperature-")) or "highest temperature" in title or "lowest temperature" in title:
            weather_rows.append(row)
    return _normalize_weather_trades(weather_rows)


def _load_quote_coverage(*, event_slugs: list[str]) -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = load_rows(
            conn,
            """
            SELECT
                MIN(mq.time) AS coverage_start_utc,
                MAX(mq.time) AS coverage_end_utc,
                COUNT(*) AS quote_row_count,
                COUNT(DISTINCT mq.market_id) AS quote_market_count
            FROM market_quotes mq
            JOIN weather_market_catalog wmc ON wmc.market_id = mq.market_id
            WHERE wmc.event_slug = ANY(%s)
            """,
            (event_slugs,),
        )
    finally:
        conn.close()
    row = rows[0] if rows else {}
    return {
        "coverage_start_utc": row.get("coverage_start_utc"),
        "coverage_end_utc": row.get("coverage_end_utc"),
        "quote_row_count": int(row.get("quote_row_count") or 0),
        "quote_market_count": int(row.get("quote_market_count") or 0),
    }


def _clip_covered_window(*, requested_start, requested_end, coverage_start, coverage_end) -> dict[str, Any]:
    covered_start = max(requested_start, coverage_start) if coverage_start else requested_start
    covered_end = min(requested_end, coverage_end) if coverage_end else requested_end
    if covered_start > covered_end:
        raise RuntimeError("No overlap between requested window and recorded market_quotes coverage")
    return {
        "covered_start_utc": covered_start,
        "covered_end_utc": covered_end,
    }


def _event_quote_bounds(
    *,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for event_slug, rows in catalog_by_event.items():
        min_time = None
        max_time = None
        market_ids = {str(row.get("market_id") or "") for row in rows}
        for market_id in market_ids:
            for outcome in ("Up", "Down"):
                series = quote_series.get((market_id, outcome))
                if not series or not series["times"]:
                    continue
                candidate_min = series["times"][0]
                candidate_max = series["times"][-1]
                min_time = candidate_min if min_time is None else min(min_time, candidate_min)
                max_time = candidate_max if max_time is None else max(max_time, candidate_max)
        result[str(event_slug)] = {
            "min_time": min_time,
            "max_time": max_time,
        }
    return result


def _mark_trade_coverage(
    trade_rows: list[dict[str, Any]],
    *,
    covered_start,
    covered_end,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    event_bounds: dict[str, dict[str, Any]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    covered: list[dict[str, Any]] = []
    uncovered: list[dict[str, Any]] = []
    for row in trade_rows:
        event_slug = str(row.get("event_slug") or "")
        timestamp_utc = row["timestamp_utc"]
        coverage_reason = None
        if timestamp_utc < covered_start or timestamp_utc > covered_end:
            coverage_reason = "outside_recorded_quote_window"
        elif event_slug not in catalog_by_event:
            coverage_reason = "event_not_in_market_catalog"
        else:
            bounds = event_bounds.get(event_slug) or {}
            if bounds.get("min_time") is None or bounds.get("max_time") is None:
                coverage_reason = "event_has_no_quote_history"
            else:
                coverage_reason = _trade_quote_coverage_reason(
                    row,
                    quote_series=quote_series,
                    quote_window_seconds=quote_window_seconds,
                    event_market_rows=catalog_by_event.get(event_slug) or [],
                )
        merged = {**row, "covered": coverage_reason is None, "coverage_reason": coverage_reason}
        if coverage_reason is None:
            covered.append(merged)
        else:
            uncovered.append(merged)
    return covered, uncovered


def _trade_quote_coverage_reason(
    trade_row: dict[str, Any],
    *,
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
    event_market_rows: list[dict[str, Any]],
) -> str | None:
    playbook_key = str(trade_row.get("public_playbook") or "")
    captured_at = trade_row["timestamp_utc"]
    market_id = str(trade_row.get("condition_id") or "")
    outcome = str(trade_row.get("outcome") or "").lower()
    if playbook_key in PAIR_PLAYBOOK_KEYS:
        up = _nearest_quote_row(
            quote_series.get((market_id, "Up")),
            captured_at=captured_at,
            quote_window_seconds=quote_window_seconds,
        )
        down = _nearest_quote_row(
            quote_series.get((market_id, "Down")),
            captured_at=captured_at,
            quote_window_seconds=quote_window_seconds,
        )
        if up is None or down is None:
            return "market_missing_quote_at_trade_time"
        return None
    if playbook_key == "neg_risk_basket":
        available = 0
        for row in event_market_rows:
            event_market_id = str(row.get("market_id") or "")
            quote = _nearest_trade_outcome_quote(
                event_market_id,
                outcome=outcome,
                captured_at=captured_at,
                quote_series=quote_series,
                quote_window_seconds=quote_window_seconds,
            )
            if quote is not None:
                available += 1
        if available < 3:
            return "event_missing_quote_at_trade_time"
        return None
    quote = _nearest_trade_outcome_quote(
        market_id,
        outcome=outcome,
        captured_at=captured_at,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
    )
    if quote is None:
        return "market_missing_quote_at_trade_time"
    return None


def _nearest_trade_outcome_quote(
    market_id: str,
    *,
    outcome: str,
    captured_at: datetime,
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> dict[str, Any] | None:
    outcome_key = "Up" if outcome == "yes" else "Down"
    return _nearest_quote_row(
        quote_series.get((market_id, outcome_key)),
        captured_at=captured_at,
        quote_window_seconds=quote_window_seconds,
    )


def _group_public_trade_sequences(
    trade_rows: list[dict[str, Any]],
    *,
    gap_seconds: int,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []
    active: dict[tuple[str, str], dict[str, Any]] = {}
    next_sequence_id = 1
    for row in sorted(trade_rows, key=lambda item: item["timestamp_utc"]):
        key = (str(row.get("condition_id") or ""), str(row.get("trade_type") or ""))
        current = active.get(key)
        if current is None or (row["timestamp_utc"] - current["last_timestamp_utc"]).total_seconds() > gap_seconds:
            current = {
                "sequence_id": next_sequence_id,
                "condition_id": str(row.get("condition_id") or ""),
                "event_slug": row.get("event_slug"),
                "city": row.get("city"),
                "local_date": row.get("local_date"),
                "trade_type": row.get("trade_type"),
                "start_timestamp_utc": row["timestamp_utc"],
                "end_timestamp_utc": row["timestamp_utc"],
                "last_timestamp_utc": row["timestamp_utc"],
                "trade_count": 0,
                "total_size": 0.0,
                "prices": [],
                "outcomes": set(),
                "trade_rows": [],
            }
            next_sequence_id += 1
            sequences.append(current)
            active[key] = current
        current["trade_count"] += 1
        current["total_size"] += safe_float(row.get("size")) or 0.0
        current["prices"].append(safe_float(row.get("price")) or 0.0)
        current["outcomes"].add(str(row.get("outcome") or ""))
        current["trade_rows"].append(row)
        current["end_timestamp_utc"] = row["timestamp_utc"]
        current["last_timestamp_utc"] = row["timestamp_utc"]
        row["sequence_id"] = current["sequence_id"]

    _annotate_neg_risk_public_baskets(trade_rows, gap_seconds=gap_seconds)

    result: list[dict[str, Any]] = []
    for sequence in sequences:
        context = _build_context_for_event(
            event_slug=str(sequence.get("event_slug") or ""),
            captured_at=sequence["start_timestamp_utc"],
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        sequence_label = _infer_public_sequence_label(sequence["trade_rows"], context)
        result.append(
            {
                "sequence_id": sequence["sequence_id"],
                "condition_id": sequence["condition_id"],
                "event_slug": sequence.get("event_slug"),
                "city": sequence.get("city"),
                "local_date": sequence.get("local_date"),
                "trade_type": sequence.get("trade_type"),
                "start_timestamp_utc": sequence["start_timestamp_utc"],
                "end_timestamp_utc": sequence["end_timestamp_utc"],
                "trade_count": sequence["trade_count"],
                "total_size": round(sequence["total_size"], 6),
                "min_price": round(min(sequence["prices"]) if sequence["prices"] else 0.0, 6),
                "max_price": round(max(sequence["prices"]) if sequence["prices"] else 0.0, 6),
                "outcomes": ",".join(sorted(sequence["outcomes"])),
                "public_playbook": sequence_label,
            }
        )
    return result


def _infer_public_sequence_label(trade_rows: list[dict[str, Any]], context) -> str:
    if not trade_rows:
        return "unsupported_public_behavior"
    if any(str(row.get("public_playbook") or "") == "neg_risk_basket" for row in trade_rows):
        return "neg_risk_basket"
    trade_type = str(trade_rows[0].get("trade_type") or "")
    if trade_type == "sell":
        return "inventory_rebalance_and_exit"
    pair_profile = _paired_sequence_profile(trade_rows)
    if pair_profile is not None:
        pair_cost = pair_profile["min_yes_price"] + pair_profile["min_no_price"]
        if pair_cost <= 1.01:
            if pair_profile["dominant_notional_fraction"] >= 0.85:
                return "asymmetric_paired_accumulation"
            return "paired_under_par"
    if any(_trade_is_tail_bucket(row, context) and (safe_float(row.get("price")) or 1.0) <= 0.10 for row in trade_rows):
        return "tail_bucket_accumulation"
    prices = [safe_float(row.get("price")) or 0.0 for row in trade_rows]
    if any(price <= 0.10 for price in prices):
        return "cheap_bucket_accumulation"
    if any(price >= 0.90 for price in prices):
        return "high_prob_bucket_accumulation"
    return "unsupported_public_behavior"


def _infer_public_trade_playbook(trade_row: dict[str, Any], *, context) -> str:
    if str(trade_row.get("trade_type") or "") == "sell":
        return "inventory_rebalance_and_exit"
    sequence_label = str(trade_row.get("public_playbook") or "")
    if sequence_label == "neg_risk_basket":
        return sequence_label
    if _is_pair_playbook(sequence_label):
        return sequence_label
    price = safe_float(trade_row.get("price")) or 0.0
    if _trade_is_tail_bucket(trade_row, context) and price <= 0.10:
        return "tail_bucket_accumulation"
    if price <= 0.10:
        return "cheap_bucket_accumulation"
    if price >= 0.90:
        return "high_prob_bucket_accumulation"
    return "unsupported_public_behavior"


def _annotate_neg_risk_public_baskets(trade_rows: list[dict[str, Any]], *, gap_seconds: int) -> None:
    clusters: list[list[dict[str, Any]]] = []
    active: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    last_seen: dict[tuple[str, str, str], datetime] = {}
    for row in sorted(trade_rows, key=lambda item: item["timestamp_utc"]):
        if str(row.get("trade_type") or "") != "buy":
            continue
        outcome = str(row.get("outcome") or "").lower()
        if outcome not in {"yes", "no"}:
            continue
        key = (str(row.get("event_slug") or ""), str(row.get("trade_type") or ""), outcome)
        current = active.get(key)
        last_timestamp = last_seen.get(key)
        if current is None or last_timestamp is None or (row["timestamp_utc"] - last_timestamp).total_seconds() > gap_seconds:
            current = []
            active[key] = current
            clusters.append(current)
        current.append(row)
        last_seen[key] = row["timestamp_utc"]
    for cluster in clusters:
        distinct_conditions = {str(row.get("condition_id") or "") for row in cluster if row.get("condition_id")}
        if len(distinct_conditions) < 3:
            continue
        prices = [safe_float(row.get("price")) for row in cluster]
        valid_prices = [float(price) for price in prices if price is not None and price > 0]
        if len(valid_prices) < 3:
            continue
        combined_cost = sum(valid_prices)
        if combined_cost > 1.01 or combined_cost < 0.60:
            continue
        for row in cluster:
            row["public_playbook"] = "neg_risk_basket"


def _paired_sequence_profile(trade_rows: list[dict[str, Any]]) -> dict[str, float] | None:
    prices_by_outcome: dict[str, list[float]] = {}
    sizes_by_outcome: dict[str, float] = {"yes": 0.0, "no": 0.0}
    notionals_by_outcome: dict[str, float] = {"yes": 0.0, "no": 0.0}
    for row in trade_rows:
        outcome = str(row.get("outcome") or "")
        if outcome not in {"yes", "no"}:
            continue
        price = safe_float(row.get("price"))
        size = safe_float(row.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        prices_by_outcome.setdefault(outcome, []).append(price)
        sizes_by_outcome[outcome] += size
        notionals_by_outcome[outcome] += price * size
    if not prices_by_outcome.get("yes") or not prices_by_outcome.get("no"):
        return None
    total_notional = notionals_by_outcome["yes"] + notionals_by_outcome["no"]
    dominant_notional = max(notionals_by_outcome["yes"], notionals_by_outcome["no"])
    dominant_side = "yes" if notionals_by_outcome["yes"] >= notionals_by_outcome["no"] else "no"
    return {
        "min_yes_price": min(prices_by_outcome["yes"]),
        "min_no_price": min(prices_by_outcome["no"]),
        "yes_size": sizes_by_outcome["yes"],
        "no_size": sizes_by_outcome["no"],
        "yes_notional": notionals_by_outcome["yes"],
        "no_notional": notionals_by_outcome["no"],
        "dominant_side": dominant_side,
        "dominant_notional_fraction": (dominant_notional / total_notional) if total_notional > 0 else 0.0,
    }


def _trade_is_tail_bucket(trade_row: dict[str, Any], context) -> bool:
    if context is None or not context.markets:
        return False
    bucket_map = {str(m.bucket_label or "").strip(): int(m.bucket_order) for m in context.markets}
    bucket_label = str(trade_row.get("bucket_label") or "").strip()
    if bucket_label not in bucket_map:
        return False
    orders = [int(m.bucket_order) for m in context.markets]
    bucket_order = bucket_map[bucket_label]
    return bucket_order in {min(orders), max(orders)}


def _split_training_holdout(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda item: item["timestamp_utc"])
    if len(ordered) < 2:
        return ordered, ordered
    split_index = max(1, int(len(ordered) * TRAIN_SPLIT_RATIO))
    split_index = min(split_index, len(ordered) - 1)
    return ordered[:split_index], ordered[split_index:]


def _prepare_parity_clone_config(base_config: dict[str, Any], *, covered_rows: list[dict[str, Any]]) -> dict[str, Any]:
    config = deepcopy(base_config)
    runtime = config.setdefault("runtime", {})
    runtime["loop_interval_seconds"] = min(float(runtime.get("loop_interval_seconds") or 5.0), 5.0)
    runtime["summary_interval_seconds"] = float(runtime.get("summary_interval_seconds") or 60.0)
    runtime["min_expected_edge_usd"] = 0.0
    runtime["min_target_shares"] = 1
    runtime["repeat_entry_cooldown_seconds"] = 0.0
    runtime["max_total_exposure_usd"] = max(float(runtime.get("max_total_exposure_usd") or 0.0), 5000.0)
    runtime["max_concurrent_positions"] = 0
    runtime["max_entry_attempts"] = 0
    runtime["total_spend_limit_usd"] = 0.0

    notional_by_playbook: dict[str, list[float]] = {}
    paired_sequence_notionals: dict[str, float] = {}
    asymmetric_dominant_fractions: list[float] = []
    pair_sequence_profiles: dict[str, dict[str, float]] = {}
    entry_notional_total = 0.0
    for row in covered_rows:
        if str(row.get("public_playbook") or "") in PAIR_PLAYBOOK_KEYS:
            sequence_id = str(row.get("sequence_id") or "")
            if sequence_id and sequence_id not in pair_sequence_profiles:
                pair_rows = [
                    candidate
                    for candidate in covered_rows
                    if str(candidate.get("sequence_id") or "") == sequence_id
                ]
                profile = _paired_sequence_profile(pair_rows)
                if profile is not None:
                    pair_sequence_profiles[sequence_id] = profile
    for row in covered_rows:
        playbook = str(row.get("public_playbook") or "")
        price = safe_float(row.get("price")) or 0.0
        size = safe_float(row.get("size")) or 0.0
        trade_type = str(row.get("trade_type") or row.get("side") or "").lower()
        if playbook and price > 0 and size > 0:
            notional_by_playbook.setdefault(playbook, []).append(price * size)
            if trade_type == "buy":
                entry_notional_total += price * size
            if playbook in PAIR_PLAYBOOK_KEYS:
                sequence_id = str(row.get("sequence_id") or "")
                if sequence_id:
                    paired_sequence_notionals[sequence_id] = paired_sequence_notionals.get(sequence_id, 0.0) + (price * size)
                    profile = pair_sequence_profiles.get(sequence_id)
                    if playbook == "asymmetric_paired_accumulation" and profile is not None:
                        asymmetric_dominant_fractions.append(profile["dominant_notional_fraction"])
    runtime["max_total_exposure_usd"] = max(float(runtime.get("max_total_exposure_usd") or 0.0), round(entry_notional_total, 2))

    for playbook_key, playbook in (config.get("playbooks") or {}).items():
        notionals = sorted(notional_by_playbook.get(playbook_key) or [])
        if bool(playbook.get("enabled", False)):
            playbook["shadow_enabled"] = True
            playbook["live_enabled"] = True
        if playbook_key in PAIR_PLAYBOOK_KEYS:
            sequence_notionals = sorted(value for value in paired_sequence_notionals.values() if value > 0)
            if sequence_notionals:
                idx = min(len(sequence_notionals) - 1, max(0, int(round((len(sequence_notionals) - 1) * 0.75))))
                playbook["sequence_budget_usd"] = max(float(playbook.get("sequence_budget_usd") or 0.0), round(sequence_notionals[idx], 2))
            elif notionals:
                idx = min(len(notionals) - 1, max(0, int(round((len(notionals) - 1) * 0.90))))
                playbook["sequence_budget_usd"] = max(float(playbook.get("sequence_budget_usd") or 0.0), round(notionals[idx] * 2.0, 2))
        elif notionals:
            idx = min(len(notionals) - 1, max(0, int(round((len(notionals) - 1) * 0.75))))
            playbook["sequence_budget_usd"] = max(float(playbook.get("sequence_budget_usd") or 0.0), round(notionals[idx], 2))
        if playbook_key == "paired_under_par":
            playbook["synthetic_pair_cost_lte"] = max(float(playbook.get("synthetic_pair_cost_lte") or 0.995), 1.02)
            playbook["stale_pair_recovery_tolerance"] = max(float(playbook.get("stale_pair_recovery_tolerance") or 0.0), 0.03)
            playbook["midpoint_confirmation_required"] = False
        if playbook_key == "asymmetric_paired_accumulation":
            dominant = sorted(value for value in asymmetric_dominant_fractions if 0.5 <= value < 1.0)
            if dominant:
                idx = min(len(dominant) - 1, max(0, int(round((len(dominant) - 1) * 0.50))))
                playbook["dominant_leg_budget_fraction"] = round(dominant[idx], 6)
            playbook["synthetic_pair_cost_lte"] = max(float(playbook.get("synthetic_pair_cost_lte") or 1.0), 1.02)
            playbook["dominant_leg_price_gte"] = min(float(playbook.get("dominant_leg_price_gte") or 0.90), 0.90)
            playbook["complementary_leg_price_lte"] = max(float(playbook.get("complementary_leg_price_lte") or 0.10), 0.10)
            playbook["midpoint_confirmation_required"] = False
    return config


def _build_trade_context_cache(
    *,
    trade_rows: list[dict[str, Any]],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> dict[tuple[str, datetime], Any]:
    cache: dict[tuple[str, datetime], Any] = {}
    for row in trade_rows:
        cache_key = (str(row.get("event_slug") or ""), row["timestamp_utc"])
        if cache_key in cache:
            continue
        cache[cache_key] = _build_context_for_event(
            event_slug=cache_key[0],
            captured_at=cache_key[1],
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
    return cache


def _evaluate_trade_time_parity(
    *,
    trade_rows: list[dict[str, Any]],
    clone_config: dict[str, Any],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
    match_window_seconds: float,
    context_cache: dict[tuple[str, datetime], Any] | None = None,
) -> dict[str, Any]:
    runtime = build_clone_runtime(clone_config, dry_run=False)
    sequence_state: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    matched_condition_side = 0
    matched_playbook = 0
    time_deltas: list[float] = []
    miss_reasons: dict[str, int] = {}
    for trade in trade_rows:
        cache_key = (str(trade.get("event_slug") or ""), trade["timestamp_utc"])
        context = context_cache.get(cache_key) if context_cache is not None else None
        if context_cache is None or cache_key not in context_cache:
            context = _build_context_for_event(
                event_slug=cache_key[0],
                captured_at=cache_key[1],
                catalog_by_event=catalog_by_event,
                quote_series=quote_series,
                quote_window_seconds=quote_window_seconds,
            )
            if context_cache is not None:
                context_cache[cache_key] = context
        public_playbook = _infer_public_trade_playbook(trade, context=context)
        base_row = {
            "timestamp_utc": trade["timestamp_utc"],
            "condition_id": trade.get("condition_id"),
            "event_slug": trade.get("event_slug"),
            "city": trade.get("city"),
            "bucket_label": trade.get("bucket_label"),
            "side": trade.get("side"),
            "outcome": trade.get("outcome"),
            "trade_type": trade.get("trade_type"),
            "price": trade.get("price"),
            "size": trade.get("size"),
            "public_playbook": public_playbook,
        }
        if context is None:
            reason = "market_not_in_replay_universe"
            rows.append({**base_row, "covered": False, "match_condition_side": False, "match_playbook": False, "match_reason": reason})
            miss_reasons[reason] = miss_reasons.get(reason, 0) + 1
            continue
        report = evaluate_clone_cycle(
            contexts=[context],
            runtime=runtime,
            captured_at=trade["timestamp_utc"],
            health_state={
                "execution_allowed": True,
                "execution_auth": {"status": "healthy", "allowed": True},
                "market_data": {"status": "healthy", "reason": "historical_quote_replay"},
                "quote_coverage_ratio": 1.0,
            },
            sequence_state=sequence_state,
            active_positions=[],
            active_market_ids=set(),
        )
        market_rows = []
        for row in report.get("cycle_rows") or []:
            if str(row.get("market_id") or "") == str(trade.get("condition_id") or ""):
                market_rows.append(row)
                continue
            if (
                str(row.get("playbook_key") or "") == "neg_risk_basket"
                and str(row.get("event_slug") or "") == str(trade.get("event_slug") or "")
                and str(row.get("side") or "") == str(trade.get("outcome") or "")
            ):
                market_rows.append(row)
        matched_row = _match_trade_to_candidate(market_rows, trade)
        match_condition_side = matched_row is not None and bool(matched_row.get("qualifies"))
        match_playbook = match_condition_side and str(matched_row.get("playbook_key") or "") == public_playbook
        match_reason = "matched"
        if not match_condition_side:
            match_reason = _trade_time_reason(market_rows, public_playbook=public_playbook)
            miss_reasons[match_reason] = miss_reasons.get(match_reason, 0) + 1
        else:
            matched_condition_side += 1
            time_deltas.append(0.0)
            if match_playbook:
                matched_playbook += 1
        rows.append(
            {
                **base_row,
                "covered": True,
                "match_condition_side": match_condition_side,
                "match_playbook": match_playbook,
                "match_reason": match_reason,
                "candidate_playbook": matched_row.get("playbook_key") if matched_row else None,
                "candidate_rejection_reasons": json.dumps((matched_row or {}).get("rejection_reasons") or []),
            }
        )
    metrics = {
        "covered_trade_count": len(trade_rows),
        "covered_trade_match_rate_condition_side": round(matched_condition_side / len(trade_rows), 6) if trade_rows else 0.0,
        "covered_trade_match_rate_playbook": round(matched_playbook / len(trade_rows), 6) if trade_rows else 0.0,
        "median_entry_time_delta_seconds": median(time_deltas) if time_deltas else None,
        "median_size_error_ratio": None,
        "false_positive_trade_count": 0,
        "top_miss_reasons": _counter_rows(miss_reasons),
    }
    return {"rows": rows, "metrics": metrics}


def _match_trade_to_candidate(market_rows: list[dict[str, Any]], trade: dict[str, Any]) -> dict[str, Any] | None:
    trade_type = str(trade.get("trade_type") or "")
    outcome = str(trade.get("outcome") or "")
    public_playbook = str(trade.get("public_playbook") or "")
    if trade_type == "sell":
        return None
    for row in market_rows:
        if not bool(row.get("qualifies")):
            continue
        playbook_key = str(row.get("playbook_key") or "")
        if playbook_key == "neg_risk_basket" and public_playbook == "neg_risk_basket":
            if str(row.get("side") or "") == outcome:
                return row
        if _is_pair_playbook(playbook_key) and playbook_key == public_playbook:
            return row
        if playbook_key == public_playbook and str(row.get("side") or "") == outcome:
            return row
    for row in market_rows:
        if not bool(row.get("qualifies")):
            continue
        playbook_key = str(row.get("playbook_key") or "")
        if _is_pair_playbook(playbook_key):
            return row
        if str(row.get("side") or "") == outcome:
            return row
    return None


def _trade_time_reason(market_rows: list[dict[str, Any]], *, public_playbook: str) -> str:
    if not market_rows:
        return "market_not_in_replay_universe"
    rejection_reasons = {
        str(reason)
        for row in market_rows
        for reason in (row.get("rejection_reasons") or [])
    }
    if "missing_pair_ask" in rejection_reasons or "missing_directional_ask" in rejection_reasons or "missing_complementary_ask" in rejection_reasons:
        return "missing_quote_pair"
    if "stale_quote" in rejection_reasons:
        return "stale_quote"
    return PLAYBOOK_REJECTION_BUCKETS.get(public_playbook, "unsupported_public_behavior")


def _default_size_model(clone_config: dict[str, Any]) -> dict[str, Any]:
    return build_clone_size_model(clone_config)


def _tune_clone_strategy(
    *,
    training_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    base_config: dict[str, Any],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
    match_window_seconds: float,
) -> dict[str, Any]:
    clone_config = deepcopy(base_config)
    size_model = _default_size_model(clone_config)
    context_cache = _build_trade_context_cache(
        trade_rows=training_rows + holdout_rows,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
    )
    logger.info("Built historical context cache for %s trade timestamps", len(context_cache))
    structural_grid = [
        ("playbooks.paired_under_par.synthetic_pair_cost_lte", [0.99, 0.995, 1.0, 1.01, 1.02, 1.03]),
        ("playbooks.paired_under_par.min_leg_price_gte", [0.0, 0.01, 0.02, 0.03]),
        ("playbooks.paired_under_par.max_leg_price_lte", [1.0, 0.99, 0.985, 0.98, 0.975]),
        ("playbooks.asymmetric_paired_accumulation.synthetic_pair_cost_lte", [0.995, 1.0, 1.01, 1.02, 1.03]),
        ("playbooks.asymmetric_paired_accumulation.dominant_leg_price_gte", [0.88, 0.90, 0.92, 0.94]),
        ("playbooks.asymmetric_paired_accumulation.complementary_leg_price_lte", [0.04, 0.06, 0.08, 0.10]),
        ("playbooks.neg_risk_basket.synthetic_basket_cost_lte", [0.97, 0.98, 0.99, 1.0]),
        ("playbooks.neg_risk_basket.min_distinct_conditions", [3, 4, 5]),
        ("playbooks.neg_risk_basket.max_unmatched_ratio", [0.20, 0.25, 0.317073, 0.40]),
        ("playbooks.cheap_bucket_accumulation.directional_price_lte", [0.04, 0.06, 0.08, 0.10]),
        ("playbooks.cheap_bucket_accumulation.complementary_price_gte", [0.90, 0.92, 0.94, 0.96]),
        ("playbooks.high_prob_bucket_accumulation.directional_price_gte", [0.90, 0.92, 0.94, 0.96]),
        ("playbooks.high_prob_bucket_accumulation.complementary_price_lte", [0.04, 0.06, 0.08, 0.10]),
        ("playbooks.high_prob_bucket_accumulation.require_dominant_bucket", [False, True]),
        ("playbooks.tail_bucket_accumulation.directional_price_lte", [0.03, 0.05, 0.08, 0.10]),
    ]
    best_structural_metrics = _evaluate_trade_time_parity(
        trade_rows=training_rows,
        clone_config=clone_config,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
        match_window_seconds=match_window_seconds,
        context_cache=context_cache,
    )["metrics"]
    for _ in range(2):
        improved = False
        for path, values in structural_grid:
            for value in values:
                candidate = deepcopy(clone_config)
                _set_nested_value(candidate, path, value)
                metrics = _evaluate_trade_time_parity(
                    trade_rows=training_rows,
                    clone_config=candidate,
                    catalog_by_event=catalog_by_event,
                    quote_series=quote_series,
                    quote_window_seconds=quote_window_seconds,
                    match_window_seconds=match_window_seconds,
                    context_cache=context_cache,
                )["metrics"]
                if _parity_score(metrics) > _parity_score(best_structural_metrics):
                    clone_config = candidate
                    best_structural_metrics = metrics
                    improved = True
        if not improved:
            break
    logger.info(
        "Structural tuning complete: match_rate=%.4f playbook_rate=%.4f",
        float(best_structural_metrics.get("covered_trade_match_rate_condition_side") or 0.0),
        float(best_structural_metrics.get("covered_trade_match_rate_playbook") or 0.0),
    )

    size_grid = [
        ("repeat_entry_cooldown_seconds", [0, 15, 30, 60, 120]),
        ("per_playbook.paired_under_par.sequence_budget_usd", [5.0, 10.0, 25.0, 50.0, 100.0]),
        ("per_playbook.asymmetric_paired_accumulation.sequence_budget_usd", [10.0, 25.0, 50.0, 100.0, 250.0]),
        ("per_playbook.asymmetric_paired_accumulation.dominant_leg_budget_fraction", [0.80, 0.85, 0.90, 0.94, 0.97]),
        ("per_playbook.neg_risk_basket.sequence_budget_usd", [10.0, 25.0, 50.0, 100.0]),
        ("per_playbook.neg_risk_basket.max_ask_size_fraction", [0.25, 0.5, 0.75, 1.0]),
        ("per_playbook.neg_risk_basket.reentry_scale", [0.5, 0.75, 1.0]),
        ("per_playbook.cheap_bucket_accumulation.sequence_budget_usd", [3.0, 5.0, 10.0, 25.0, 50.0]),
        ("per_playbook.high_prob_bucket_accumulation.sequence_budget_usd", [3.0, 5.0, 10.0, 25.0, 50.0]),
        ("per_playbook.tail_bucket_accumulation.sequence_budget_usd", [2.0, 5.0, 10.0, 20.0]),
        ("per_playbook.cheap_bucket_accumulation.max_ask_size_fraction", [0.25, 0.5, 0.75, 1.0]),
        ("per_playbook.high_prob_bucket_accumulation.max_ask_size_fraction", [0.25, 0.5, 0.75, 1.0]),
        ("per_playbook.tail_bucket_accumulation.max_ask_size_fraction", [0.25, 0.5, 0.75, 1.0]),
        ("per_playbook.cheap_bucket_accumulation.reentry_scale", [0.5, 0.75, 1.0]),
        ("per_playbook.high_prob_bucket_accumulation.reentry_scale", [0.5, 0.75, 1.0]),
    ]
    best_size_metrics = _evaluate_size_fit(
        trade_rows=training_rows,
        clone_config=clone_config,
        size_model=size_model,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
        context_cache=context_cache,
    )
    for _ in range(2):
        improved = False
        for path, values in size_grid:
            for value in values:
                candidate_size = deepcopy(size_model)
                _set_nested_value(candidate_size, path, value)
                metrics = _evaluate_size_fit(
                    trade_rows=training_rows,
                    clone_config=clone_config,
                    size_model=candidate_size,
                    catalog_by_event=catalog_by_event,
                    quote_series=quote_series,
                    quote_window_seconds=quote_window_seconds,
                    context_cache=context_cache,
                )
                if _parity_score(metrics) > _parity_score(best_size_metrics):
                    size_model = candidate_size
                    best_size_metrics = metrics
                    improved = True
        if not improved:
            break
    logger.info(
        "Size tuning complete: median_size_error=%.4f",
        float(best_size_metrics.get("median_size_error_ratio") or 0.0),
    )

    event_bounds = _event_quote_bounds(catalog_by_event=catalog_by_event, quote_series=quote_series)
    best_replay_metrics = _run_full_replay(
        trade_rows=training_rows,
        clone_config=clone_config,
        size_model=size_model,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        event_bounds=event_bounds,
        quote_window_seconds=quote_window_seconds,
        match_window_seconds=match_window_seconds,
    )["metrics"]
    replay_grid = [
        ("repeat_entry_cooldown_seconds", [0, 5, 10, 15, 30, 60]),
        ("per_playbook.asymmetric_paired_accumulation.sequence_budget_usd", [10.0, 25.0, 50.0, 100.0, 250.0, 425.0]),
        ("per_playbook.asymmetric_paired_accumulation.reentry_scale", [1.0, 1.25, 1.5, 2.0]),
        ("per_playbook.asymmetric_paired_accumulation.dominant_leg_budget_fraction", [0.85, 0.90, 0.92, 0.94, 0.97]),
        ("per_playbook.neg_risk_basket.sequence_budget_usd", [10.0, 25.0, 50.0, 100.0]),
        ("per_playbook.neg_risk_basket.reentry_scale", [0.75, 1.0, 1.25]),
    ]
    for _ in range(2):
        improved = False
        for path, values in replay_grid:
            for value in values:
                candidate_size = deepcopy(size_model)
                _set_nested_value(candidate_size, path, value)
                metrics = _run_full_replay(
                    trade_rows=training_rows,
                    clone_config=clone_config,
                    size_model=candidate_size,
                    catalog_by_event=catalog_by_event,
                    quote_series=quote_series,
                    event_bounds=event_bounds,
                    quote_window_seconds=quote_window_seconds,
                    match_window_seconds=match_window_seconds,
                )["metrics"]
                if _parity_score(metrics) > _parity_score(best_replay_metrics):
                    size_model = candidate_size
                    best_replay_metrics = metrics
                    improved = True
        if not improved:
            break
    logger.info(
        "Replay tuning complete: match_rate=%.4f playbook_rate=%.4f size_error=%.4f",
        float(best_replay_metrics.get("covered_trade_match_rate_condition_side") or 0.0),
        float(best_replay_metrics.get("covered_trade_match_rate_playbook") or 0.0),
        float(best_replay_metrics.get("median_size_error_ratio") or 0.0),
    )

    training_metrics = _run_full_replay(
        trade_rows=training_rows,
        clone_config=clone_config,
        size_model=size_model,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        event_bounds=event_bounds,
        quote_window_seconds=quote_window_seconds,
        match_window_seconds=match_window_seconds,
    )["metrics"]
    holdout_metrics = _run_full_replay(
        trade_rows=holdout_rows,
        clone_config=apply_clone_size_model(clone_config, size_model),
        size_model=size_model,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        event_bounds=event_bounds,
        quote_window_seconds=quote_window_seconds,
        match_window_seconds=match_window_seconds,
    )["metrics"]
    return {
        "clone_config": apply_clone_size_model(clone_config, size_model),
        "size_model": size_model,
        "training_metrics": training_metrics,
        "holdout_metrics": holdout_metrics,
        "strategy_parameters": {
            "playbooks": apply_clone_size_model(clone_config, size_model).get("playbooks") or {},
            "size_model": size_model,
        },
    }


def _parity_score(metrics: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(metrics.get("covered_trade_match_rate_condition_side") or 0.0),
        float(metrics.get("covered_trade_match_rate_playbook") or 0.0),
        -float(metrics.get("median_entry_time_delta_seconds") or 999999.0),
        -float(metrics.get("median_size_error_ratio") or 999999.0),
        -float(metrics.get("false_positive_trade_count") or 999999.0),
    )


def _evaluate_size_fit(
    *,
    trade_rows: list[dict[str, Any]],
    clone_config: dict[str, Any],
    size_model: dict[str, Any],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
    context_cache: dict[tuple[str, datetime], Any] | None = None,
) -> dict[str, Any]:
    runtime = build_clone_runtime(clone_config, dry_run=False)
    sequence_state: dict[str, dict[str, Any]] = {}
    entry_counts: dict[tuple[str, str, str], int] = {}
    matched_condition_side = 0
    matched_playbook = 0
    size_errors: list[float] = []
    for trade in trade_rows:
        cache_key = (str(trade.get("event_slug") or ""), trade["timestamp_utc"])
        context = context_cache.get(cache_key) if context_cache is not None else None
        if context_cache is None or cache_key not in context_cache:
            context = _build_context_for_event(
                event_slug=cache_key[0],
                captured_at=cache_key[1],
                catalog_by_event=catalog_by_event,
                quote_series=quote_series,
                quote_window_seconds=quote_window_seconds,
            )
            if context_cache is not None:
                context_cache[cache_key] = context
        if context is None:
            continue
        public_playbook = _infer_public_trade_playbook(trade, context=context)
        report = evaluate_clone_cycle(
            contexts=[context],
            runtime=runtime,
            captured_at=trade["timestamp_utc"],
            health_state={
                "execution_allowed": True,
                "execution_auth": {"status": "healthy", "allowed": True},
                "market_data": {"status": "healthy", "reason": "historical_quote_replay"},
                "quote_coverage_ratio": 1.0,
            },
            sequence_state=sequence_state,
            active_positions=[],
            active_market_ids=set(),
        )
        market_rows = [
            row for row in report.get("candidates") or []
            if str(row.get("market_id") or "") == str(trade.get("condition_id") or "")
        ]
        candidate = _match_trade_to_candidate(market_rows, trade)
        if candidate is None:
            continue
        matched_condition_side += 1
        if str(candidate.get("playbook_key") or "") == public_playbook:
            matched_playbook += 1
        if _is_pair_playbook(str(candidate.get("playbook_key") or "")):
            plan = plan_paired_entry(candidate, runtime, active_exposure_usd=0.0)
        else:
            plan = plan_directional_entry(candidate, runtime, active_exposure_usd=0.0)
        if plan is None:
            size_errors.append(1.0)
            continue
        adjusted = _apply_size_model(plan, candidate=candidate, size_model=size_model, entry_counts=entry_counts)
        if adjusted is None:
            size_errors.append(1.0)
            continue
        simulated_size = _planned_trade_size_for_trade(
            adjusted,
            condition_id=str(trade.get("condition_id") or ""),
            outcome=str(trade.get("outcome") or ""),
        )
        public_size = safe_float(trade.get("size")) or 0.0
        if public_size > 0:
            size_errors.append(abs(simulated_size - public_size) / public_size)
        outcome_key = "paired" if _is_pair_playbook(str(candidate.get("playbook_key") or "")) else str(trade.get("outcome") or "")
        entry_key = (str(trade.get("condition_id") or ""), outcome_key, str(candidate.get("playbook_key") or ""))
        entry_counts[entry_key] = entry_counts.get(entry_key, 0) + 1
    covered_count = len(trade_rows)
    return {
        "covered_trade_count": covered_count,
        "covered_trade_match_rate_condition_side": round(matched_condition_side / covered_count, 6) if covered_count else 0.0,
        "covered_trade_match_rate_playbook": round(matched_playbook / covered_count, 6) if covered_count else 0.0,
        "median_entry_time_delta_seconds": 0.0 if matched_condition_side else None,
        "median_size_error_ratio": median(size_errors) if size_errors else None,
        "false_positive_trade_count": 0,
        "top_miss_reasons": [],
    }


def _set_nested_value(payload: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current = payload
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _run_full_replay(
    *,
    trade_rows: list[dict[str, Any]],
    clone_config: dict[str, Any],
    size_model: dict[str, Any],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    event_bounds: dict[str, dict[str, Any]],
    quote_window_seconds: int,
    match_window_seconds: float,
) -> dict[str, Any]:
    if not trade_rows:
        return {"replay_trades": [], "blocked_candidates": [], "matched_rows": [], "metrics": _empty_metrics()}
    runtime = build_clone_runtime(clone_config, dry_run=False)
    loop_seconds = max(1.0, float((clone_config.get("runtime") or {}).get("loop_interval_seconds") or weather_config.DEFAULT_LOOP_INTERVAL_SECONDS))
    event_slugs = sorted({str(row.get("event_slug") or "") for row in trade_rows if row.get("event_slug")})
    tick_times = _build_tick_times(trade_rows[0]["timestamp_utc"], trade_rows[-1]["timestamp_utc"], loop_seconds)
    active_positions: list[dict[str, Any]] = []
    replay_trades: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    sequence_state: dict[str, dict[str, Any]] = {}
    entry_counts: dict[tuple[str, str, str], int] = {}
    spent_usd = 0.0
    next_position_id = 1
    runtime_cfg = clone_config.get("runtime") or {}
    total_spend_limit = float(runtime_cfg.get("total_spend_limit_usd") or 0.0)
    max_exposure = float(runtime_cfg.get("max_total_exposure_usd") or weather_config.DEFAULT_MAX_TOTAL_EXPOSURE_USD)
    max_positions = int(runtime_cfg.get("max_concurrent_positions") or weather_config.DEFAULT_MAX_CONCURRENT_POSITIONS)
    max_entries_per_tick = _max_entry_attempt_limit(runtime_cfg)

    for captured_at in tick_times:
        active_positions, neg_risk_exit_trades = _simulate_neg_risk_exits(
            active_positions=active_positions,
            captured_at=captured_at,
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        replay_trades.extend(neg_risk_exit_trades)
        active_positions, exit_trades = _simulate_directional_exits(
            active_positions=active_positions,
            captured_at=captured_at,
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        replay_trades.extend(exit_trades)
        contexts = []
        for event_slug in event_slugs:
            bounds = event_bounds.get(event_slug) or {}
            min_time = bounds.get("min_time")
            max_time = bounds.get("max_time")
            if min_time is not None and captured_at < min_time:
                continue
            if max_time is not None and captured_at > max_time:
                continue
            context = _build_context_for_event(
                event_slug=event_slug,
                captured_at=captured_at,
                catalog_by_event=catalog_by_event,
                quote_series=quote_series,
                quote_window_seconds=quote_window_seconds,
            )
            if context is not None:
                contexts.append(context)
        if not contexts:
            continue
        report = evaluate_clone_cycle(
            contexts=contexts,
            runtime=runtime,
            captured_at=captured_at,
            health_state={
                "execution_allowed": True,
                "execution_auth": {"status": "healthy", "allowed": True},
                "market_data": {"status": "healthy", "reason": "historical_replay"},
                "quote_coverage_ratio": 1.0,
            },
            sequence_state=sequence_state,
            active_positions=active_positions,
            active_market_ids={str(position.get("market_id") or "") for position in active_positions if position.get("closed_at") is None},
        )
        active_exposure = round(sum(float(position.get("total_entry_cost") or 0.0) for position in active_positions if position.get("closed_at") is None), 6)
        entries_this_tick = 0
        for candidate in report.get("candidates") or []:
            if not (candidate.get("qualifies") and candidate.get("live_eligible")):
                continue
            playbook_key = str(candidate.get("playbook_key") or "")
            candidate_side = str(candidate.get("side") or "paired")
            cooldown_key = (str(candidate.get("market_id") or ""), candidate_side, str(candidate.get("playbook_key") or ""))
            cooldown_block = _reentry_cooldown_blocked(
                replay_trades=replay_trades,
                cooldown_key=cooldown_key,
                captured_at=captured_at,
                cooldown_seconds=float(size_model.get("repeat_entry_cooldown_seconds") or 0.0),
            )
            if cooldown_block:
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": "repeat_entry_rule_mismatch"})
                continue
            if len([position for position in active_positions if position.get("closed_at") is None]) >= max_positions:
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": "exposure_or_spend_cap_blocked"})
                continue
            if max_exposure > 0 and active_exposure >= max_exposure:
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": "exposure_or_spend_cap_blocked"})
                continue
            if total_spend_limit > 0 and spent_usd >= total_spend_limit:
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": "exposure_or_spend_cap_blocked"})
                continue
            if playbook_key == "neg_risk_basket":
                plan = plan_neg_risk_entry(candidate, runtime, active_exposure_usd=active_exposure)
            elif _is_pair_playbook(str(candidate.get("playbook_key") or "")):
                plan = plan_paired_entry(candidate, runtime, active_exposure_usd=active_exposure)
            else:
                plan = plan_directional_entry(candidate, runtime, active_exposure_usd=active_exposure)
            if plan is None:
                continue
            plan = _apply_size_model(plan, candidate=candidate, size_model=size_model, entry_counts=entry_counts)
            if plan is None:
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": "order_size_model_mismatch"})
                continue
            entry_rows, position_row = _simulate_entry_from_plan(
                plan=plan,
                candidate=candidate,
                captured_at=captured_at,
                position_id=next_position_id,
            )
            if position_row is None:
                continue
            next_position_id += 1
            replay_trades.extend(entry_rows)
            active_positions.append(position_row)
            spent_usd += sum(float(row.get("notional_usd") or 0.0) for row in entry_rows if str(row.get("trade_type") or "") == "buy")
            entry_counts[cooldown_key] = entry_counts.get(cooldown_key, 0) + 1
            active_exposure = round(sum(float(position.get("total_entry_cost") or 0.0) for position in active_positions if position.get("closed_at") is None), 6)
            entries_this_tick += 1
            if max_entries_per_tick > 0 and entries_this_tick >= max_entries_per_tick:
                break

    matched_rows, metrics = _compare_replay_to_public(
        public_rows=trade_rows,
        replay_rows=replay_trades,
        match_window_seconds=match_window_seconds,
    )
    return {
        "replay_trades": replay_trades,
        "blocked_candidates": blocked_candidates,
        "matched_rows": matched_rows,
        "metrics": metrics,
    }


def _candidate_brief(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "condition_id": candidate.get("market_id"),
        "event_slug": candidate.get("event_slug"),
        "city": candidate.get("city"),
        "bucket_label": candidate.get("bucket_label"),
        "playbook_key": candidate.get("playbook_key"),
        "side": candidate.get("side"),
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "covered_trade_count": 0,
        "covered_trade_match_rate_condition_side": 0.0,
        "covered_trade_match_rate_playbook": 0.0,
        "median_entry_time_delta_seconds": None,
        "median_size_error_ratio": None,
        "false_positive_trade_count": 0,
        "false_positive_notional_usd": 0.0,
        "false_positive_pnl_proxy_usd": 0.0,
        "public_notional_usd": 0.0,
        "replay_notional_usd": 0.0,
        "public_pnl_proxy_usd": 0.0,
        "replay_pnl_proxy_usd": 0.0,
        "replay_pnl_proxy_ratio": None,
        "playbook_pnl_proxy": [],
        "top_miss_reasons": [],
    }


def _build_tick_times(start, end, loop_seconds: float) -> list[Any]:
    ticks = []
    current = start
    while current <= end:
        ticks.append(current)
        current = current + timedelta(seconds=loop_seconds)
    return ticks


def _max_entry_attempt_limit(runtime_cfg: dict[str, Any]) -> int:
    raw_value = runtime_cfg.get("max_entry_attempts")
    if raw_value is None:
        return 1
    return int(raw_value)


def _reentry_cooldown_blocked(*, replay_trades: list[dict[str, Any]], cooldown_key: tuple[str, str, str], captured_at, cooldown_seconds: float) -> bool:
    if cooldown_seconds <= 0:
        return False
    condition_id, side, playbook_key = cooldown_key
    for row in reversed(replay_trades):
        if str(row.get("condition_id") or "") != condition_id:
            continue
        if str(row.get("playbook_key") or "") != playbook_key:
            continue
        if str(row.get("outcome") or "paired") != side and not (side == "paired" and row.get("outcome") in {"yes", "no"}):
            continue
        return (captured_at - row["timestamp_utc"]).total_seconds() < cooldown_seconds
    return False


def _pair_targets_from_budget(
    *,
    yes_price: float,
    no_price: float,
    yes_ask_size: float | None,
    no_ask_size: float | None,
    sequence_budget: float,
    max_fraction: float,
    reentry_scale: float,
    dominant_leg_budget_fraction: float | None,
) -> tuple[int, int]:
    if sequence_budget <= 0:
        return 0, 0
    effective_budget = max(0.0, sequence_budget * reentry_scale)
    if dominant_leg_budget_fraction is None:
        target_shares = floor(effective_budget / (yes_price + no_price))
        size_cap = min(yes_ask_size, no_ask_size) if yes_ask_size is not None and no_ask_size is not None else None
        if size_cap is not None:
            target_shares = min(target_shares, floor(size_cap * max_fraction))
        target_shares = target_shares - (target_shares % 1)
        return target_shares, target_shares

    dominant_fraction = min(max(float(dominant_leg_budget_fraction), 0.5), 0.995)
    dominant_side = "yes" if yes_price >= no_price else "no"
    yes_budget = effective_budget * (dominant_fraction if dominant_side == "yes" else (1.0 - dominant_fraction))
    no_budget = effective_budget * (dominant_fraction if dominant_side == "no" else (1.0 - dominant_fraction))

    yes_target = floor(yes_budget / yes_price)
    no_target = floor(no_budget / no_price)
    if yes_ask_size is not None:
        yes_target = min(yes_target, floor(yes_ask_size * max_fraction))
    if no_ask_size is not None:
        no_target = min(no_target, floor(no_ask_size * max_fraction))
    return yes_target, no_target


def _planned_trade_size_for_outcome(plan: dict[str, Any], outcome: str) -> float:
    if str(plan.get("playbook_key") or "") == "neg_risk_basket":
        legs = list(plan.get("legs") or [])
        if outcome not in {"yes", "no"}:
            return 0.0
        return float(
            sum(
                safe_float(leg.get("target_shares")) or 0.0
                for leg in legs
                if str(plan.get("side") or "") == outcome
            )
        )
    if _is_pair_playbook(str(plan.get("playbook_key") or "")):
        if outcome == "yes":
            return safe_float(plan.get("yes_target_shares")) or safe_float(plan.get("target_shares")) or 0.0
        if outcome == "no":
            return safe_float(plan.get("no_target_shares")) or safe_float(plan.get("target_shares")) or 0.0
    return safe_float(plan.get("target_shares")) or 0.0


def _planned_trade_size_for_trade(plan: dict[str, Any], *, condition_id: str, outcome: str) -> float:
    if str(plan.get("playbook_key") or "") == "neg_risk_basket":
        for leg in plan.get("legs") or []:
            if str(leg.get("market_id") or "") == condition_id:
                return safe_float(leg.get("target_shares")) or 0.0
        return 0.0
    return _planned_trade_size_for_outcome(plan, outcome)


def _apply_size_model(
    plan: dict[str, Any],
    *,
    candidate: dict[str, Any],
    size_model: dict[str, Any],
    entry_counts: dict[tuple[str, str, str], int],
) -> dict[str, Any] | None:
    playbook_key = str(plan.get("playbook_key") or "")
    settings = ((size_model.get("per_playbook") or {}).get(playbook_key) or {})
    sequence_budget = safe_float(settings.get("sequence_budget_usd")) or safe_float(plan.get("sequence_budget_usd")) or 0.0
    max_fraction = safe_float(settings.get("max_ask_size_fraction")) or 1.0
    reentry_scale = safe_float(settings.get("reentry_scale")) or 1.0
    if _is_pair_playbook(playbook_key):
        yes_size = safe_float(candidate.get("yes_ask_size"))
        no_size = safe_float(candidate.get("no_ask_size"))
        cost_per_share = safe_float(plan.get("combined_cost")) or 0.0
        entry_key = (str(plan.get("condition_id") or ""), "paired", playbook_key)
    elif playbook_key == "neg_risk_basket":
        cost_per_share = safe_float(plan.get("combined_cost")) or 0.0
        entry_key = (str(plan.get("condition_id") or ""), str(plan.get("side") or ""), playbook_key)
    else:
        available_size = safe_float(plan.get("available_size"))
        if available_size is None:
            available_size = safe_float(candidate.get("available_size"))
        cost_per_share = safe_float(plan.get("price")) or 0.0
        entry_key = (str(plan.get("condition_id") or ""), str(plan.get("side") or ""), playbook_key)
    if cost_per_share <= 0:
        return None
    repeat_count = entry_counts.get(entry_key, 0)
    adjusted = dict(plan)
    adjusted["sequence_budget_usd"] = sequence_budget
    if _is_pair_playbook(playbook_key):
        yes_price = safe_float(plan.get("yes_price"))
        no_price = safe_float(plan.get("no_price"))
        if yes_price is None:
            yes_price = safe_float(candidate.get("yes_ask"))
        if no_price is None:
            no_price = safe_float(candidate.get("no_ask"))
        yes_price = yes_price or 0.0
        no_price = no_price or 0.0
        if yes_price <= 0 or no_price <= 0:
            return None
        dominant_fraction = safe_float(settings.get("dominant_leg_budget_fraction"))
        if playbook_key == "asymmetric_paired_accumulation" and dominant_fraction is None:
            dominant_fraction = safe_float(plan.get("dominant_leg_budget_fraction")) or 0.94
        yes_target_shares, no_target_shares = _pair_targets_from_budget(
            yes_price=yes_price,
            no_price=no_price,
            yes_ask_size=yes_size,
            no_ask_size=no_size,
            sequence_budget=sequence_budget,
            max_fraction=max_fraction,
            reentry_scale=reentry_scale ** repeat_count,
            dominant_leg_budget_fraction=dominant_fraction if playbook_key == "asymmetric_paired_accumulation" else None,
        )
        paired_target_shares = min(yes_target_shares, no_target_shares)
        if paired_target_shares <= 0:
            return None
        adjusted["yes_target_shares"] = yes_target_shares
        adjusted["no_target_shares"] = no_target_shares
        adjusted["target_shares"] = paired_target_shares
        adjusted["total_target_cost"] = round((yes_target_shares * yes_price) + (no_target_shares * no_price), 6)
        adjusted["expected_edge_usd"] = round((1.0 - cost_per_share) * paired_target_shares, 6)
    elif playbook_key == "neg_risk_basket":
        legs = list(plan.get("legs") or [])
        if not legs:
            return None
        effective_budget = max(0.0, sequence_budget * (reentry_scale ** repeat_count))
        per_leg_budget = effective_budget / max(len(legs), 1)
        adjusted_legs: list[dict[str, Any]] = []
        for leg in legs:
            price = safe_float(leg.get("price")) or 0.0
            available_size = safe_float(leg.get("available_size"))
            if price <= 0:
                continue
            target_shares = floor(per_leg_budget / price)
            if available_size is not None and available_size > 0:
                target_shares = min(target_shares, floor(available_size * max_fraction))
            if target_shares <= 0:
                continue
            adjusted_legs.append(
                {
                    **leg,
                    "target_shares": int(target_shares),
                    "available_size": available_size,
                }
            )
        required_conditions = int(
            safe_float((candidate.get("signal_data") or {}).get("selected_condition_count"))
            or safe_float(plan.get("selected_condition_count"))
            or 3
        )
        if len(adjusted_legs) < required_conditions:
            return None
        adjusted["legs"] = adjusted_legs
        adjusted["selected_condition_count"] = len(adjusted_legs)
        adjusted["target_shares"] = int(sum(int(leg.get("target_shares") or 0) for leg in adjusted_legs))
        adjusted["combined_cost"] = round(sum((safe_float(leg.get("price")) or 0.0) for leg in adjusted_legs), 6)
        adjusted["total_target_cost"] = round(
            sum((safe_float(leg.get("price")) or 0.0) * int(leg.get("target_shares") or 0) for leg in adjusted_legs),
            6,
        )
        adjusted["expected_edge_usd"] = round(
            max(0.0, 1.0 - float(adjusted.get("combined_cost") or 0.0))
            * min(int(leg.get("target_shares") or 0) for leg in adjusted_legs),
            6,
        )
    else:
        target_shares = int(plan.get("target_shares") or 0)
        target_shares = floor(target_shares * (reentry_scale ** repeat_count))
        if available_size is not None and available_size > 0:
            target_shares = min(target_shares, floor(available_size * max_fraction))
        target_shares = min(target_shares, floor(sequence_budget / cost_per_share)) if sequence_budget > 0 else target_shares
        if target_shares <= 0:
            return None
        adjusted["target_shares"] = target_shares
        profit_take = safe_float(plan.get("profit_take_price"))
        adjusted["expected_edge_usd"] = round(max(0.0, (profit_take or cost_per_share) - cost_per_share) * target_shares, 6)
    return adjusted


def _simulate_entry_from_plan(*, plan: dict[str, Any], candidate: dict[str, Any], captured_at, position_id: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    playbook_key = str(plan.get("playbook_key") or "")
    target_shares = int(plan.get("target_shares") or 0)
    if target_shares <= 0:
        return [], None
    if playbook_key == "neg_risk_basket":
        side = str(plan.get("side") or "")
        legs = list(plan.get("legs") or [])
        if side not in {"yes", "no"} or not legs:
            return [], None
        rows = [
            _replay_trade_row(
                captured_at=captured_at,
                condition_id=str(leg.get("market_id") or ""),
                event_slug=str(plan.get("event_slug") or ""),
                city=str(plan.get("city") or ""),
                local_date=plan.get("local_date"),
                bucket_label=str(leg.get("bucket_label") or ""),
                playbook_key=playbook_key,
                trade_type="buy",
                outcome=side,
                size=int(leg.get("target_shares") or 0),
                price=safe_float(leg.get("price")) or 0.0,
            )
            for leg in legs
            if int(leg.get("target_shares") or 0) > 0 and (safe_float(leg.get("price")) or 0.0) > 0.0
        ]
        if not rows:
            return [], None
        position = {
            "id": position_id,
            "market_id": str(plan.get("condition_id") or ""),
            "event_slug": str(plan.get("event_slug") or ""),
            "city": str(plan.get("city") or ""),
            "local_date": plan.get("local_date"),
            "bucket_label": str(plan.get("bucket_label") or ""),
            "playbook_key": playbook_key,
            "side": side,
            "status": "open_neg_risk_basket",
            "opened_at": captured_at,
            "closed_at": None,
            "legs": [
                {
                    "market_id": str(leg.get("market_id") or ""),
                    "bucket_label": str(leg.get("bucket_label") or ""),
                    "target_shares": int(leg.get("target_shares") or 0),
                }
                for leg in legs
            ],
            "force_flatten_minutes_before_end": float(
                safe_float((candidate.get("signal_data") or {}).get("force_flatten_minutes_before_end"))
                or safe_float(plan.get("force_flatten_minutes_before_end"))
                or 120.0
            ),
            "max_unmatched_ratio": safe_float((candidate.get("signal_data") or {}).get("max_unmatched_ratio")),
            "selected_condition_count": len(legs),
            "total_entry_cost": round(sum(float(row.get("notional_usd") or 0.0) for row in rows), 6),
        }
        return rows, position
    if _is_pair_playbook(playbook_key):
        yes_price = safe_float(plan.get("yes_price")) or 0.0
        no_price = safe_float(plan.get("no_price")) or 0.0
        yes_target_shares = int(plan.get("yes_target_shares") or target_shares)
        no_target_shares = int(plan.get("no_target_shares") or target_shares)
        if yes_price <= 0 or no_price <= 0:
            return [], None
        rows = [
            _replay_trade_row(
                captured_at=captured_at,
                condition_id=str(plan.get("condition_id") or ""),
                event_slug=str(plan.get("event_slug") or ""),
                city=str(plan.get("city") or ""),
                local_date=plan.get("local_date"),
                bucket_label=str(plan.get("bucket_label") or ""),
                playbook_key=playbook_key,
                trade_type="buy",
                outcome="yes",
                size=yes_target_shares,
                price=yes_price,
            ),
            _replay_trade_row(
                captured_at=captured_at,
                condition_id=str(plan.get("condition_id") or ""),
                event_slug=str(plan.get("event_slug") or ""),
                city=str(plan.get("city") or ""),
                local_date=plan.get("local_date"),
                bucket_label=str(plan.get("bucket_label") or ""),
                playbook_key=playbook_key,
                trade_type="buy",
                outcome="no",
                size=no_target_shares,
                price=no_price,
            ),
        ]
        position = {
            "id": position_id,
            "market_id": str(plan.get("condition_id") or ""),
            "event_slug": str(plan.get("event_slug") or ""),
            "city": str(plan.get("city") or ""),
            "local_date": plan.get("local_date"),
            "bucket_label": str(plan.get("bucket_label") or ""),
            "playbook_key": playbook_key,
            "status": "open_paired",
            "opened_at": captured_at,
            "closed_at": None,
            "total_entry_cost": round((yes_price * yes_target_shares) + (no_price * no_target_shares), 6),
        }
        return rows, position
    side = str(plan.get("side") or "")
    price = safe_float(plan.get("price")) or 0.0
    if side not in {"yes", "no"} or price <= 0:
        return [], None
    row = _replay_trade_row(
        captured_at=captured_at,
        condition_id=str(plan.get("condition_id") or ""),
        event_slug=str(plan.get("event_slug") or ""),
        city=str(plan.get("city") or ""),
        local_date=plan.get("local_date"),
        bucket_label=str(plan.get("bucket_label") or ""),
        playbook_key=playbook_key,
        trade_type="buy",
        outcome=side,
        size=target_shares,
        price=price,
    )
    position = {
        "id": position_id,
        "market_id": str(plan.get("condition_id") or ""),
        "event_slug": str(plan.get("event_slug") or ""),
        "city": str(plan.get("city") or ""),
        "local_date": plan.get("local_date"),
        "bucket_label": str(plan.get("bucket_label") or ""),
        "playbook_key": playbook_key,
        "side": side,
        "status": "open_directional",
        "opened_at": captured_at,
        "closed_at": None,
        "remaining_shares": target_shares,
        "profit_take_price": safe_float(plan.get("profit_take_price")),
        "minimum_hold_seconds": safe_float(plan.get("minimum_hold_seconds")) or 0.0,
        "force_flatten_minutes_before_end": 120.0,
        "total_entry_cost": round(price * target_shares, 6),
    }
    return [row], position


def _simulate_neg_risk_exits(
    *,
    active_positions: list[dict[str, Any]],
    captured_at,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    remaining: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    for position in active_positions:
        if position.get("closed_at") is not None or str(position.get("status") or "") != "open_neg_risk_basket":
            remaining.append(position)
            continue
        context = _build_context_for_event(
            event_slug=str(position.get("event_slug") or ""),
            captured_at=captured_at,
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        if context is None:
            remaining.append(position)
            continue
        market_map = {str(market.market_id or ""): market for market in context.markets}
        legs = list(position.get("legs") or [])
        if not legs:
            remaining.append(position)
            continue
        side = str(position.get("side") or "")
        quoted_legs = 0
        current_basket_value = 0.0
        exitable_legs: list[tuple[dict[str, Any], float]] = []
        ended_at = None
        for leg in legs:
            market = market_map.get(str(leg.get("market_id") or ""))
            if market is None:
                continue
            ended_at = market.ended_at or ended_at
            exit_price = safe_float(market.yes_bid if side == "yes" else market.no_bid)
            if exit_price is None:
                continue
            quoted_legs += 1
            current_basket_value += exit_price
            exitable_legs.append((leg, exit_price))
        should_exit = False
        if ended_at is not None:
            minutes_to_end = (ended_at - captured_at).total_seconds() / 60.0
            if minutes_to_end <= float(position.get("force_flatten_minutes_before_end") or 0.0):
                should_exit = True
        expected_min_legs = int(position.get("selected_condition_count") or len(legs) or 0)
        if expected_min_legs > 0 and quoted_legs < expected_min_legs:
            should_exit = True
        max_unmatched_ratio = safe_float(position.get("max_unmatched_ratio"))
        if (
            max_unmatched_ratio is not None
            and side == "yes"
            and quoted_legs > 0
            and max(0.0, 1.0 - current_basket_value) > max_unmatched_ratio
        ):
            should_exit = True
        if not should_exit or not exitable_legs:
            remaining.append(position)
            continue
        for leg, exit_price in exitable_legs:
            shares = int(leg.get("target_shares") or 0)
            if shares <= 0:
                continue
            replay_rows.append(
                _replay_trade_row(
                    captured_at=captured_at,
                    condition_id=str(leg.get("market_id") or ""),
                    event_slug=str(position.get("event_slug") or ""),
                    city=str(position.get("city") or ""),
                    local_date=position.get("local_date"),
                    bucket_label=str(leg.get("bucket_label") or ""),
                    playbook_key="inventory_rebalance_and_exit",
                    trade_type="sell",
                    outcome=side,
                    size=shares,
                    price=exit_price,
                )
            )
    return remaining, replay_rows


def _simulate_directional_exits(
    *,
    active_positions: list[dict[str, Any]],
    captured_at,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    remaining: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    for position in active_positions:
        if position.get("closed_at") is not None or str(position.get("status") or "") != "open_directional":
            remaining.append(position)
            continue
        context = _build_context_for_event(
            event_slug=str(position.get("event_slug") or ""),
            captured_at=captured_at,
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        if context is None:
            remaining.append(position)
            continue
        market = next((item for item in context.markets if str(item.market_id) == str(position.get("market_id") or "")), None)
        if market is None:
            remaining.append(position)
            continue
        side = str(position.get("side") or "")
        exit_price = safe_float(market.yes_bid if side == "yes" else market.no_bid)
        if exit_price is None:
            remaining.append(position)
            continue
        opened_at = position.get("opened_at")
        if opened_at is None:
            remaining.append(position)
            continue
        age_seconds = max(0.0, (captured_at - opened_at).total_seconds())
        if age_seconds < float(position.get("minimum_hold_seconds") or 0.0):
            remaining.append(position)
            continue
        should_exit = False
        profit_take = safe_float(position.get("profit_take_price"))
        if profit_take is not None and exit_price >= profit_take:
            should_exit = True
        ended_at = market.ended_at
        if ended_at is not None:
            minutes_to_end = (ended_at - captured_at).total_seconds() / 60.0
            if minutes_to_end <= float(position.get("force_flatten_minutes_before_end") or 0.0):
                should_exit = True
        if not should_exit:
            remaining.append(position)
            continue
        shares = int(position.get("remaining_shares") or 0)
        replay_rows.append(
            _replay_trade_row(
                captured_at=captured_at,
                condition_id=str(position.get("market_id") or ""),
                event_slug=str(position.get("event_slug") or ""),
                city=str(position.get("city") or ""),
                local_date=position.get("local_date"),
                bucket_label=str(position.get("bucket_label") or ""),
                playbook_key="inventory_rebalance_and_exit",
                trade_type="sell",
                outcome=side,
                size=shares,
                price=exit_price,
            )
        )
        closed = dict(position)
        closed["closed_at"] = captured_at
        closed["status"] = "closed_directional"
    return remaining, replay_rows


def _replay_trade_row(
    *,
    captured_at,
    condition_id: str,
    event_slug: str,
    city: str,
    local_date,
    bucket_label: str,
    playbook_key: str,
    trade_type: str,
    outcome: str,
    size: int,
    price: float,
) -> dict[str, Any]:
    return {
        "timestamp_utc": captured_at,
        "condition_id": condition_id,
        "event_slug": event_slug,
        "city": city,
        "local_date": local_date,
        "bucket_label": bucket_label,
        "playbook_key": playbook_key,
        "trade_type": trade_type,
        "side": trade_type,
        "outcome": outcome,
        "size": size,
        "price": round(price, 6),
        "notional_usd": round(float(size) * float(price), 6),
    }


def _trade_notional_usd(row: dict[str, Any]) -> float:
    notional = safe_float(row.get("notional_usd"))
    if notional is not None:
        return round(abs(notional), 6)
    price = safe_float(row.get("price")) or 0.0
    size = safe_float(row.get("size")) or 0.0
    return round(abs(price * size), 6)


def _trade_cashflow_proxy_usd(row: dict[str, Any]) -> float:
    trade_type = str(row.get("trade_type") or row.get("side") or "").lower()
    notional = _trade_notional_usd(row)
    if trade_type in {"sell", "redeem"}:
        return round(notional, 6)
    return round(-notional, 6)


def _pnl_proxy_ratio(public_pnl_proxy_usd: float, replay_pnl_proxy_usd: float) -> float | None:
    if public_pnl_proxy_usd > 0:
        return round(replay_pnl_proxy_usd / public_pnl_proxy_usd, 6)
    if public_pnl_proxy_usd == 0:
        return 1.0 if replay_pnl_proxy_usd >= 0 else 0.0
    return None


def _playbook_cashflow_summary(*, public_rows: list[dict[str, Any]], replay_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_by_playbook: dict[str, dict[str, float]] = {}
    replay_by_playbook: dict[str, dict[str, float]] = {}
    for row in public_rows:
        playbook_key = str(row.get("public_playbook") or "unsupported_public_behavior")
        bucket = public_by_playbook.setdefault(playbook_key, {"public_notional_usd": 0.0, "public_pnl_proxy_usd": 0.0})
        bucket["public_notional_usd"] += _trade_notional_usd(row)
        bucket["public_pnl_proxy_usd"] += _trade_cashflow_proxy_usd(row)
    for row in replay_rows:
        playbook_key = str(row.get("playbook_key") or "unsupported_public_behavior")
        bucket = replay_by_playbook.setdefault(playbook_key, {"replay_notional_usd": 0.0, "replay_pnl_proxy_usd": 0.0})
        bucket["replay_notional_usd"] += _trade_notional_usd(row)
        bucket["replay_pnl_proxy_usd"] += _trade_cashflow_proxy_usd(row)
    keys = sorted(set(public_by_playbook) | set(replay_by_playbook))
    result = []
    for key in keys:
        public_bucket = public_by_playbook.get(key) or {}
        replay_bucket = replay_by_playbook.get(key) or {}
        public_pnl = round(float(public_bucket.get("public_pnl_proxy_usd") or 0.0), 6)
        replay_pnl = round(float(replay_bucket.get("replay_pnl_proxy_usd") or 0.0), 6)
        result.append(
            {
                "playbook_key": key,
                "public_notional_usd": round(float(public_bucket.get("public_notional_usd") or 0.0), 6),
                "replay_notional_usd": round(float(replay_bucket.get("replay_notional_usd") or 0.0), 6),
                "public_pnl_proxy_usd": public_pnl,
                "replay_pnl_proxy_usd": replay_pnl,
                "replay_pnl_proxy_ratio": _pnl_proxy_ratio(public_pnl, replay_pnl),
            }
        )
    return result


def _compare_replay_to_public(
    *,
    public_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    match_window_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unmatched_replay = set(range(len(replay_rows)))
    matched_rows: list[dict[str, Any]] = []
    miss_reasons: dict[str, int] = {}
    deltas: list[float] = []
    size_errors: list[float] = []
    playbook_matches = 0
    for public in public_rows:
        matches: list[tuple[float, int, dict[str, Any]]] = []
        for idx, replay in enumerate(replay_rows):
            if idx not in unmatched_replay:
                continue
            if str(replay.get("condition_id") or "") != str(public.get("condition_id") or ""):
                continue
            if str(replay.get("trade_type") or "") != str(public.get("trade_type") or ""):
                continue
            if str(replay.get("outcome") or "") != str(public.get("outcome") or ""):
                continue
            delta = abs((replay["timestamp_utc"] - public["timestamp_utc"]).total_seconds())
            if delta <= match_window_seconds:
                matches.append((delta, idx, replay))
        if matches:
            matches.sort(key=lambda item: (item[0], abs((safe_float(item[2].get("size")) or 0.0) - (safe_float(public.get("size")) or 0.0))))
            delta, idx, replay = matches[0]
            unmatched_replay.discard(idx)
            public_playbook = str(public.get("public_playbook") or "")
            replay_playbook = str(replay.get("playbook_key") or "")
            size_ratio = _size_error_ratio(public, replay)
            deltas.append(delta)
            size_errors.append(size_ratio)
            if replay_playbook == public_playbook:
                playbook_matches += 1
            matched_rows.append(
                {
                    "timestamp_utc": public["timestamp_utc"],
                    "condition_id": public.get("condition_id"),
                    "event_slug": public.get("event_slug"),
                    "city": public.get("city"),
                    "bucket_label": public.get("bucket_label"),
                    "public_playbook": public_playbook,
                    "replay_playbook": replay_playbook,
                    "trade_type": public.get("trade_type"),
                    "outcome": public.get("outcome"),
                    "delta_seconds": round(delta, 6),
                    "size_error_ratio": round(size_ratio, 6),
                    "public_notional_usd": _trade_notional_usd(public),
                    "replay_notional_usd": _trade_notional_usd(replay),
                    "public_pnl_proxy_usd": _trade_cashflow_proxy_usd(public),
                    "replay_pnl_proxy_usd": _trade_cashflow_proxy_usd(replay),
                    "matched": True,
                }
            )
        else:
            miss_reasons["no_replay_match"] = miss_reasons.get("no_replay_match", 0) + 1
            matched_rows.append(
                {
                    "timestamp_utc": public["timestamp_utc"],
                    "condition_id": public.get("condition_id"),
                    "event_slug": public.get("event_slug"),
                    "city": public.get("city"),
                    "bucket_label": public.get("bucket_label"),
                    "public_playbook": public.get("public_playbook"),
                    "replay_playbook": None,
                    "trade_type": public.get("trade_type"),
                    "outcome": public.get("outcome"),
                    "delta_seconds": None,
                    "size_error_ratio": None,
                    "public_notional_usd": _trade_notional_usd(public),
                    "replay_notional_usd": 0.0,
                    "public_pnl_proxy_usd": _trade_cashflow_proxy_usd(public),
                    "replay_pnl_proxy_usd": 0.0,
                    "matched": False,
                }
            )
    public_notional_usd = round(sum(_trade_notional_usd(row) for row in public_rows), 6)
    replay_notional_usd = round(sum(_trade_notional_usd(row) for row in replay_rows), 6)
    public_pnl_proxy_usd = round(sum(_trade_cashflow_proxy_usd(row) for row in public_rows), 6)
    replay_pnl_proxy_usd = round(sum(_trade_cashflow_proxy_usd(row) for row in replay_rows), 6)
    false_positive_notional_usd = round(sum(_trade_notional_usd(replay_rows[idx]) for idx in unmatched_replay), 6)
    false_positive_pnl_proxy_usd = round(sum(_trade_cashflow_proxy_usd(replay_rows[idx]) for idx in unmatched_replay), 6)
    metrics = {
        "covered_trade_count": len(public_rows),
        "covered_trade_match_rate_condition_side": round(sum(1 for row in matched_rows if row["matched"]) / len(public_rows), 6) if public_rows else 0.0,
        "covered_trade_match_rate_playbook": round(playbook_matches / len(public_rows), 6) if public_rows else 0.0,
        "median_entry_time_delta_seconds": median(deltas) if deltas else None,
        "median_size_error_ratio": median(size_errors) if size_errors else None,
        "false_positive_trade_count": len(unmatched_replay),
        "false_positive_notional_usd": false_positive_notional_usd,
        "false_positive_pnl_proxy_usd": false_positive_pnl_proxy_usd,
        "public_notional_usd": public_notional_usd,
        "replay_notional_usd": replay_notional_usd,
        "public_pnl_proxy_usd": public_pnl_proxy_usd,
        "replay_pnl_proxy_usd": replay_pnl_proxy_usd,
        "replay_pnl_proxy_ratio": _pnl_proxy_ratio(public_pnl_proxy_usd, replay_pnl_proxy_usd),
        "playbook_pnl_proxy": _playbook_cashflow_summary(public_rows=public_rows, replay_rows=replay_rows),
        "top_miss_reasons": _counter_rows(miss_reasons),
    }
    return matched_rows, metrics


def _size_error_ratio(public: dict[str, Any], replay: dict[str, Any]) -> float:
    public_size = safe_float(public.get("size")) or 0.0
    replay_size = safe_float(replay.get("size")) or 0.0
    if public_size <= 0:
        return 1.0
    return abs(replay_size - public_size) / public_size


def _classify_public_parity_misses(
    *,
    covered_rows: list[dict[str, Any]],
    trade_time_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    match_window_seconds: float,
) -> list[dict[str, Any]]:
    trade_time_map = {
        (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        ): row
        for row in trade_time_rows
    }
    classified: list[dict[str, Any]] = []
    for row in covered_rows:
        key = (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        )
        trade_time = trade_time_map.get(key) or {}
        best_replay = _nearest_replay_trade(
            row,
            replay_rows=replay_rows,
            blocked_rows=blocked_rows,
            match_window_seconds=match_window_seconds,
        )
        miss_bucket = _classify_miss_bucket(
            public_row=row,
            trade_time_row=trade_time,
            nearest_match=best_replay,
        )
        if miss_bucket not in MISS_BUCKETS and miss_bucket != "matched":
            miss_bucket = "unsupported_public_behavior"
        classified.append(
            {
                "timestamp_utc": row["timestamp_utc"],
                "condition_id": row.get("condition_id"),
                "event_slug": row.get("event_slug"),
                "city": row.get("city"),
                "bucket_label": row.get("bucket_label"),
                "trade_type": row.get("trade_type"),
                "outcome": row.get("outcome"),
                "public_playbook": row.get("public_playbook"),
                "miss_bucket": miss_bucket,
                "notional_usd": _trade_notional_usd(row),
                "cashflow_proxy_usd": _trade_cashflow_proxy_usd(row),
                "replay_playbook": best_replay.get("playbook_key") if best_replay else None,
                "replay_delta_seconds": best_replay.get("delta_seconds") if best_replay else None,
                "replay_size_error_ratio": best_replay.get("size_error_ratio") if best_replay else None,
            }
        )
    return classified


def _nearest_replay_trade(
    public_row: dict[str, Any],
    *,
    replay_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    match_window_seconds: float,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for replay in replay_rows:
        if str(replay.get("condition_id") or "") != str(public_row.get("condition_id") or ""):
            continue
        if str(replay.get("trade_type") or "") != str(public_row.get("trade_type") or ""):
            continue
        if str(replay.get("outcome") or "") != str(public_row.get("outcome") or ""):
            continue
        delta = abs((replay["timestamp_utc"] - public_row["timestamp_utc"]).total_seconds())
        matches.append(
            {
                **replay,
                "delta_seconds": round(delta, 6),
                "size_error_ratio": round(_size_error_ratio(public_row, replay), 6),
                "within_match_window": delta <= match_window_seconds,
            }
        )
    if matches:
        matches.sort(key=lambda item: (item["delta_seconds"], item["size_error_ratio"]))
        return matches[0]
    for blocked in blocked_rows:
        if str(blocked.get("condition_id") or "") != str(public_row.get("condition_id") or ""):
            continue
        if str(blocked.get("side") or "paired") not in {str(public_row.get("outcome") or ""), "paired"}:
            continue
        delta = abs((blocked["timestamp_utc"] - public_row["timestamp_utc"]).total_seconds())
        return {**blocked, "delta_seconds": round(delta, 6), "blocked": True}
    return None


def _classify_miss_bucket(
    *,
    public_row: dict[str, Any],
    trade_time_row: dict[str, Any],
    nearest_match: dict[str, Any] | None,
) -> str:
    public_playbook = str(public_row.get("public_playbook") or "")
    if nearest_match and bool(nearest_match.get("within_match_window")):
        replay_playbook = str(nearest_match.get("playbook_key") or "")
        size_error_ratio = safe_float(nearest_match.get("size_error_ratio")) or 0.0
        if replay_playbook != public_playbook:
            return PLAYBOOK_REJECTION_BUCKETS.get(public_playbook, "unsupported_public_behavior")
        if size_error_ratio > 0.25:
            return "order_size_model_mismatch"
        return "matched"
    if nearest_match and nearest_match.get("blocked"):
        return str(nearest_match.get("block_reason") or "repeat_entry_rule_mismatch")
    if nearest_match and not bool(nearest_match.get("within_match_window")):
        return "repeat_entry_rule_mismatch"
    reason = str(trade_time_row.get("match_reason") or "").strip()
    if reason in MISS_BUCKETS:
        return reason
    if public_playbook == "inventory_rebalance_and_exit":
        return "closeout_rule_mismatch"
    return PLAYBOOK_REJECTION_BUCKETS.get(public_playbook, "unsupported_public_behavior")


def _filter_metrics_to_rows(matched_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_keys = {
        (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        )
        for row in target_rows
    }
    rows = [
        row for row in matched_rows
        if (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        )
        in target_keys
    ]
    covered_count = len(rows)
    matched_count = sum(1 for row in rows if row.get("matched"))
    playbook_count = sum(1 for row in rows if row.get("matched") and str(row.get("replay_playbook") or "") == str(row.get("public_playbook") or ""))
    deltas = [safe_float(row.get("delta_seconds")) for row in rows if safe_float(row.get("delta_seconds")) is not None and row.get("matched")]
    size_errors = [safe_float(row.get("size_error_ratio")) for row in rows if safe_float(row.get("size_error_ratio")) is not None and row.get("matched")]
    public_notional_usd = round(sum(float(row.get("public_notional_usd") or 0.0) for row in rows), 6)
    replay_notional_usd = round(sum(float(row.get("replay_notional_usd") or 0.0) for row in rows), 6)
    public_pnl_proxy_usd = round(sum(float(row.get("public_pnl_proxy_usd") or 0.0) for row in rows), 6)
    replay_pnl_proxy_usd = round(sum(float(row.get("replay_pnl_proxy_usd") or 0.0) for row in rows), 6)
    public_rows = [
        {
            "public_playbook": row.get("public_playbook"),
            "trade_type": row.get("trade_type"),
            "price": 1.0,
            "size": float(row.get("public_notional_usd") or 0.0),
            "notional_usd": float(row.get("public_notional_usd") or 0.0),
        }
        for row in rows
        if float(row.get("public_notional_usd") or 0.0) > 0.0
    ]
    replay_rows = [
        {
            "playbook_key": row.get("replay_playbook"),
            "trade_type": row.get("trade_type"),
            "price": 1.0,
            "size": float(row.get("replay_notional_usd") or 0.0),
            "notional_usd": float(row.get("replay_notional_usd") or 0.0),
        }
        for row in rows
        if float(row.get("replay_notional_usd") or 0.0) > 0.0 and row.get("replay_playbook")
    ]
    return {
        "covered_trade_count": covered_count,
        "covered_trade_match_rate_condition_side": round(matched_count / covered_count, 6) if covered_count else 0.0,
        "covered_trade_match_rate_playbook": round(playbook_count / covered_count, 6) if covered_count else 0.0,
        "median_entry_time_delta_seconds": median(deltas) if deltas else None,
        "median_size_error_ratio": median(size_errors) if size_errors else None,
        "false_positive_trade_count": 0,
        "false_positive_notional_usd": 0.0,
        "false_positive_pnl_proxy_usd": 0.0,
        "public_notional_usd": public_notional_usd,
        "replay_notional_usd": replay_notional_usd,
        "public_pnl_proxy_usd": public_pnl_proxy_usd,
        "replay_pnl_proxy_usd": replay_pnl_proxy_usd,
        "replay_pnl_proxy_ratio": _pnl_proxy_ratio(public_pnl_proxy_usd, replay_pnl_proxy_usd),
        "playbook_pnl_proxy": _playbook_cashflow_summary(public_rows=public_rows, replay_rows=replay_rows),
    }


def _filter_rows_to_trade_set(rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_keys = {
        (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        )
        for row in target_rows
    }
    return [
        row
        for row in rows
        if (
            row["timestamp_utc"],
            str(row.get("condition_id") or ""),
            str(row.get("trade_type") or ""),
            str(row.get("outcome") or ""),
        )
        in target_keys
    ]


def _playbook_metric(metrics: dict[str, Any], playbook_key: str) -> dict[str, Any] | None:
    for row in metrics.get("playbook_pnl_proxy") or []:
        if str(row.get("playbook_key") or "") == playbook_key:
            return row
    return None


def _aggregate_pair_proxy(metrics: dict[str, Any]) -> dict[str, float | None]:
    public_pnl = 0.0
    replay_pnl = 0.0
    found = False
    for playbook_key in (*PAIR_PLAYBOOK_KEYS, "inventory_rebalance_and_exit"):
        row = _playbook_metric(metrics, playbook_key)
        if row is None:
            continue
        found = True
        public_pnl += float(row.get("public_pnl_proxy_usd") or 0.0)
        replay_pnl += float(row.get("replay_pnl_proxy_usd") or 0.0)
    return {
        "public_pnl_proxy_usd": round(public_pnl, 6) if found else 0.0,
        "replay_pnl_proxy_usd": round(replay_pnl, 6) if found else 0.0,
        "replay_pnl_proxy_ratio": _pnl_proxy_ratio(public_pnl, replay_pnl),
    }


def _miss_bucket_notional_summary(miss_rows: list[dict[str, Any]], *, min_notional_usd: float) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = {}
    for row in miss_rows:
        key = str(row.get("miss_bucket") or "")
        bucket = buckets.setdefault(key, {"count": 0.0, "notional_usd": 0.0, "cashflow_proxy_usd": 0.0})
        bucket["count"] += 1.0
        bucket["notional_usd"] += float(row.get("notional_usd") or 0.0)
        bucket["cashflow_proxy_usd"] += float(row.get("cashflow_proxy_usd") or 0.0)
    result = []
    for key, payload in sorted(buckets.items(), key=lambda item: (-item[1]["notional_usd"], item[0])):
        if payload["notional_usd"] < min_notional_usd:
            continue
        result.append(
            {
                "miss_bucket": key,
                "count": int(payload["count"]),
                "notional_usd": round(payload["notional_usd"], 6),
                "cashflow_proxy_usd": round(payload["cashflow_proxy_usd"], 6),
            }
        )
    return result


def _deployment_gate_result(
    *,
    holdout_metrics: dict[str, Any],
    miss_rows: list[dict[str, Any]],
    parity_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parity_config = parity_config or {}
    unexplained_by_condition: dict[str, int] = {}
    total_by_condition: dict[str, int] = {}
    for row in miss_rows:
        condition_id = str(row.get("condition_id") or "")
        total_by_condition[condition_id] = total_by_condition.get(condition_id, 0) + 1
        if str(row.get("miss_bucket") or "") not in {"matched", "order_size_model_mismatch", "repeat_entry_rule_mismatch"}:
            unexplained_by_condition[condition_id] = unexplained_by_condition.get(condition_id, 0) + 1
    top_condition_failures = []
    for condition_id, total in sorted(total_by_condition.items(), key=lambda item: -item[1])[:10]:
        unexplained = unexplained_by_condition.get(condition_id, 0)
        ratio = (unexplained / total) if total else 0.0
        top_condition_failures.append({"condition_id": condition_id, "unexplained_miss_ratio": round(ratio, 6), "trade_count": total})
    pair_proxy = _aggregate_pair_proxy(holdout_metrics)
    replay_ratio = holdout_metrics.get("replay_pnl_proxy_ratio")
    pair_ratio = pair_proxy.get("replay_pnl_proxy_ratio")
    replay_pnl_gate_passed = (
        float(holdout_metrics.get("replay_pnl_proxy_usd") or 0.0)
        >= float(holdout_metrics.get("public_pnl_proxy_usd") or 0.0)
        if float(holdout_metrics.get("public_pnl_proxy_usd") or 0.0) <= 0.0
        else (replay_ratio is not None and float(replay_ratio) >= float(parity_config.get("holdout_replay_pnl_proxy_ratio_gte") or 0.75))
    )
    pair_pnl_gate_passed = (
        float(pair_proxy.get("replay_pnl_proxy_usd") or 0.0)
        >= float(pair_proxy.get("public_pnl_proxy_usd") or 0.0)
        if float(pair_proxy.get("public_pnl_proxy_usd") or 0.0) <= 0.0
        else (pair_ratio is not None and float(pair_ratio) >= float(parity_config.get("holdout_pair_replay_pnl_proxy_ratio_gte") or 0.85))
    )
    passed = (
        float(holdout_metrics.get("covered_trade_match_rate_condition_side") or 0.0)
        >= float(parity_config.get("holdout_condition_side_match_rate_gte") or 0.70)
        and float(holdout_metrics.get("covered_trade_match_rate_playbook") or 0.0)
        >= float(parity_config.get("holdout_playbook_match_rate_gte") or 0.60)
        and (
            holdout_metrics.get("median_entry_time_delta_seconds") is not None
            and float(holdout_metrics.get("median_entry_time_delta_seconds") or 999999.0)
            <= float(parity_config.get("holdout_median_entry_delta_seconds_lte") or 45.0)
        )
        and (
            holdout_metrics.get("median_size_error_ratio") is not None
            and float(holdout_metrics.get("median_size_error_ratio") or 999999.0)
            <= float(parity_config.get("holdout_median_size_error_ratio_lte") or 0.35)
        )
        and replay_pnl_gate_passed
        and pair_pnl_gate_passed
        and all(item["unexplained_miss_ratio"] <= 0.40 for item in top_condition_failures)
    )
    return {
        "passed": passed,
        "top_condition_failures": top_condition_failures,
        "holdout_pair_pnl_proxy": pair_proxy,
        "holdout_replay_pnl_gate_passed": replay_pnl_gate_passed,
        "holdout_pair_pnl_gate_passed": pair_pnl_gate_passed,
        "top_miss_buckets_by_notional": _miss_bucket_notional_summary(
            miss_rows,
            min_notional_usd=float(parity_config.get("notional_miss_bucket_min_usd") or 25.0),
        ),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({str(key) for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _build_markdown_report(
    *,
    wallet_target: dict[str, Any],
    summary: dict[str, Any],
    uncovered_rows: list[dict[str, Any]],
    grouped_sequences: list[dict[str, Any]],
    miss_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# ColdMath Public Parity",
        "",
        "## Window",
        f"- Artifact ID: `{summary.get('artifact_id')}`",
        f"- Wallet: `{wallet_target['proxy_wallet']}`",
        f"- Requested start UTC: `{summary['requested_window']['requested_start_utc'].isoformat()}`",
        f"- Requested end UTC: `{summary['requested_window']['requested_end_utc'].isoformat()}`",
        f"- Covered start UTC: `{summary['covered_window']['covered_start_utc'].isoformat()}`",
        f"- Covered end UTC: `{summary['covered_window']['covered_end_utc'].isoformat()}`",
        "",
        "## Counts",
        f"- ColdMath public trades: `{summary['coldmath_trade_count']}`",
        f"- Covered trades: `{summary['covered_trade_count']}`",
        f"- Uncovered trades: `{summary['uncovered_trade_count']}`",
        "",
        "## Money Proxy",
        f"- Public notional USD: `{summary['full_replay_metrics']['public_notional_usd']}`",
        f"- Replay notional USD: `{summary['full_replay_metrics']['replay_notional_usd']}`",
        f"- Public PnL proxy USD: `{summary['full_replay_metrics']['public_pnl_proxy_usd']}`",
        f"- Replay PnL proxy USD: `{summary['full_replay_metrics']['replay_pnl_proxy_usd']}`",
        f"- Replay/Public PnL proxy ratio: `{summary['full_replay_metrics']['replay_pnl_proxy_ratio']}`",
        "",
        "## Holdout Metrics",
        f"- Condition+side match rate: `{summary['holdout_metrics']['covered_trade_match_rate_condition_side']}`",
        f"- Playbook match rate: `{summary['holdout_metrics']['covered_trade_match_rate_playbook']}`",
        f"- Median entry delta seconds: `{summary['holdout_metrics']['median_entry_time_delta_seconds']}`",
        f"- Median size error ratio: `{summary['holdout_metrics']['median_size_error_ratio']}`",
        f"- Holdout replay PnL proxy USD: `{summary['holdout_metrics']['replay_pnl_proxy_usd']}`",
        f"- Holdout public PnL proxy USD: `{summary['holdout_metrics']['public_pnl_proxy_usd']}`",
        f"- Holdout replay/public PnL proxy ratio: `{summary['holdout_metrics']['replay_pnl_proxy_ratio']}`",
        f"- Holdout pair replay/public PnL proxy ratio: `{summary['deployment_gate']['holdout_pair_pnl_proxy']['replay_pnl_proxy_ratio']}`",
        "",
        "## Deployment Gate",
        f"- Passed: `{summary['deployment_gate']['passed']}`",
        "",
        "## Top Miss Buckets",
    ]
    miss_counts: dict[str, int] = {}
    for row in miss_rows:
        label = str(row.get("miss_bucket") or "")
        miss_counts[label] = miss_counts.get(label, 0) + 1
    for item in _counter_rows(miss_counts):
        lines.append(f"- `{item['label']}`: `{item['count']}`")

    lines.extend(["", "## Top Miss Buckets By Notional"])
    for item in summary["deployment_gate"].get("top_miss_buckets_by_notional") or []:
        lines.append(
            f"- `{item['miss_bucket']}`: notional=`{item['notional_usd']}` cashflow_proxy=`{item['cashflow_proxy_usd']}` count=`{item['count']}`"
        )

    lines.extend(["", "## Top Public Sequence Playbooks"])
    sequence_counts: dict[str, int] = {}
    for row in grouped_sequences:
        label = str(row.get("public_playbook") or "")
        sequence_counts[label] = sequence_counts.get(label, 0) + 1
    for item in _counter_rows(sequence_counts):
        lines.append(f"- `{item['label']}`: `{item['count']}`")

    lines.extend(["", "## Playbook PnL Proxy"])
    for row in summary["full_replay_metrics"].get("playbook_pnl_proxy") or []:
        lines.append(
            f"- `{row['playbook_key']}`: public_pnl_proxy=`{row['public_pnl_proxy_usd']}` replay_pnl_proxy=`{row['replay_pnl_proxy_usd']}` ratio=`{row['replay_pnl_proxy_ratio']}`"
        )

    lines.extend(["", "## Uncovered Trades"])
    if not uncovered_rows:
        lines.append("- None")
    else:
        for row in uncovered_rows[:30]:
            lines.append(
                f"- `{row['timestamp_utc'].isoformat()}` | `{row.get('city')}` `{row.get('bucket_label')}` | `{row.get('coverage_reason')}`"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
