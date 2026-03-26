"""Compare ColdMath public weather trades with weather merge scan telemetry."""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from analysis.coldmath_window_compare import DEFAULT_LOG_PATH, run_window_comparison
from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.utils import ensure_dir, safe_float

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure weather merge parity against ColdMath public trades")
    parser.add_argument("--profile", type=str, default="ColdMath")
    parser.add_argument("--wallet", type=str)
    parser.add_argument("--log-path", type=str, default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--fallback-log-path", type=str, default=None)
    parser.add_argument("--lxc-date-is", type=str, default=None)
    parser.add_argument("--log-timezone", type=str, default=None)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--heartbeat-gap-seconds", type=float, default=180.0)
    parser.add_argument("--match-window-seconds", type=float, default=120.0)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_merge_parity(args)
    logger.info("Merge parity complete with matched ratio %.4f", result["summary"]["matched_trade_ratio"])
    return 0


def run_merge_parity(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    comparison_result = run_window_comparison(
        argparse.Namespace(
            profile=args.profile,
            wallet=args.wallet,
            log_path=args.log_path,
            fallback_log_path=args.fallback_log_path,
            lxc_date_is=args.lxc_date_is,
            log_timezone=args.log_timezone,
            window_hours=args.window_hours,
            heartbeat_gap_seconds=args.heartbeat_gap_seconds,
            output_dir=str(
                ensure_dir(
                    Path(args.output_dir).resolve()
                    if args.output_dir
                    else Path(__file__).resolve().parents[2] / "src" / "results" / "wallet_forensics" / "coldmath_merge_parity"
                )
            ),
            verbose=args.verbose,
        )
    )
    output_dir = Path(comparison_result["report_path"]).resolve().parent
    window = comparison_result["window"]

    merge_data = _load_merge_debug_data(
        window_start_utc=window["window_start_utc"],
        window_end_utc=window["window_end_utc"],
        condition_ids={str(row.get("condition_id") or "") for row in comparison_result["coldmath"]["trade_rows"] if row.get("condition_id")},
    )
    parity = _classify_merge_parity(
        trade_rows=comparison_result["coldmath"]["trade_rows"],
        market_scan_rows=merge_data["market_scan_rows"],
        summary_rows=merge_data["summary_rows"],
        catalog_rows=merge_data["catalog_rows"],
        match_window_seconds=float(args.match_window_seconds),
    )
    report_path = output_dir / "coldmath_merge_parity_report.md"
    summary_path = output_dir / "coldmath_merge_parity_summary.json"
    report_path.write_text(
        _build_markdown_report(comparison_result=comparison_result, parity=parity),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(parity, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {
        "comparison_result": comparison_result,
        "summary": parity["summary"],
        "report_path": str(report_path),
        "summary_path": str(summary_path),
    }


def _load_merge_debug_data(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    condition_ids: set[str],
) -> dict[str, Any]:
    conn = get_connection()
    try:
        market_scan_rows: list[dict[str, Any]] = []
        if _table_exists(conn, "weather_merge_market_scans"):
            market_scan_rows = load_rows(
                conn,
                """
                SELECT
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
                FROM weather_merge_market_scans
                WHERE captured_at BETWEEN %s AND %s
                ORDER BY captured_at ASC
                """,
                (window_start_utc, window_end_utc),
            )
        summary_rows = load_rows(
            conn,
            """
            SELECT logged_at, log_type, message, data
            FROM bot_logs
            WHERE logged_at BETWEEN %s AND %s
              AND log_type IN ('weather_merge_summary', 'weather_merge_stand_down', 'weather_merge_resumed')
            ORDER BY logged_at ASC
            """,
            (window_start_utc, window_end_utc),
        )
        catalog_rows = load_rows(
            conn,
            """
            SELECT
                market_id,
                event_slug,
                city,
                local_date,
                bucket_label,
                timezone,
                active,
                eligible,
                eligibility_reason,
                started_at,
                ended_at
            FROM weather_market_catalog
            WHERE market_id = ANY(%s)
            """,
            (list(condition_ids),),
        ) if condition_ids else []
    finally:
        conn.close()
    return {
        "market_scan_rows": market_scan_rows,
        "summary_rows": summary_rows,
        "catalog_rows": catalog_rows,
    }


def _table_exists(conn, table_name: str) -> bool:
    rows = load_rows(
        conn,
        "SELECT to_regclass(%s) AS relation_name",
        (f"public.{table_name}",),
    )
    if not rows:
        return False
    return bool(rows[0].get("relation_name"))


def _classify_trade_group_pattern(rows: list[dict[str, Any]]) -> str:
    prices = sorted(price for price in (safe_float(row.get("price")) for row in rows) if price is not None)
    if not prices:
        return "unknown"
    if prices[0] <= 0.10 and prices[-1] >= 0.90:
        pair_sum = prices[0] + prices[-1]
        if pair_sum < 1.0:
            return "paired_complementary_under_par"
        if pair_sum <= 1.01:
            return "paired_complementary_near_par"
        return "paired_complementary_above_par"
    if prices[-1] <= 0.10:
        return "directional_low_tail"
    if prices[0] >= 0.90:
        return "directional_high_tail"
    return "mixed_midrange"


def _latest_prior_scan(
    *,
    scans_by_market: dict[str, list[dict[str, Any]]],
    market_id: str,
    trade_ts: datetime,
    match_window_seconds: float,
) -> dict[str, Any] | None:
    rows = scans_by_market.get(market_id) or []
    best: dict[str, Any] | None = None
    best_age: float | None = None
    for row in rows:
        captured_at = row.get("captured_at")
        if not isinstance(captured_at, datetime):
            continue
        delta = (trade_ts - captured_at).total_seconds()
        if delta < 0 or delta > match_window_seconds:
            continue
        if best_age is None or delta < best_age:
            best = row
            best_age = delta
    return best


def _latest_prior_summary(summary_rows: list[dict[str, Any]], trade_ts: datetime) -> dict[str, Any] | None:
    best = None
    for row in summary_rows:
        logged_at = row.get("logged_at")
        if not isinstance(logged_at, datetime) or logged_at > trade_ts:
            continue
        best = row
    return best


def _classify_merge_parity(
    *,
    trade_rows: list[dict[str, Any]],
    market_scan_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    match_window_seconds: float,
) -> dict[str, Any]:
    scans_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in market_scan_rows:
        scans_by_market[str(row.get("market_id") or "")].append(row)
    catalog_by_market = {str(row.get("market_id") or ""): row for row in catalog_rows}

    grouped_trades: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trade_rows:
        grouped_trades[str(trade.get("condition_id") or "")].append(trade)
    pattern_by_market = {
        market_id: _classify_trade_group_pattern(rows)
        for market_id, rows in grouped_trades.items()
    }

    matched_rows: list[dict[str, Any]] = []
    classified_rows: list[dict[str, Any]] = []
    root_cause_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()

    for trade in trade_rows:
        market_id = str(trade.get("condition_id") or "")
        trade_ts = trade["timestamp_utc"]
        scan_row = _latest_prior_scan(
            scans_by_market=scans_by_market,
            market_id=market_id,
            trade_ts=trade_ts,
            match_window_seconds=match_window_seconds,
        )
        latest_summary = _latest_prior_summary(summary_rows, trade_ts)
        summary_data = dict(latest_summary.get("data") or {}) if latest_summary else {}
        stand_down_reason = str(summary_data.get("stand_down_reason") or "").strip() or None
        catalog_row = catalog_by_market.get(market_id)

        if scan_row and bool(scan_row.get("qualifies")):
            root_cause = "matched_candidate"
            matched_rows.append(trade)
            details = {"scan_captured_at": scan_row.get("captured_at")}
        elif scan_row:
            reasons = list(scan_row.get("rejection_reasons") or [])
            root_cause = f"scan_rejected:{reasons[0] if reasons else 'unknown'}"
            details = {
                "scan_captured_at": scan_row.get("captured_at"),
                "rejection_reasons": reasons,
                "combined_cost": safe_float(scan_row.get("combined_cost")),
                "combined_mid_cost": safe_float(scan_row.get("combined_mid_cost")),
            }
        elif stand_down_reason:
            root_cause = f"guard_blocked:{stand_down_reason}"
            details = {"stand_down_reason": stand_down_reason}
        elif catalog_row is None:
            root_cause = "market_missing_from_catalog"
            details = {}
        elif not bool(catalog_row.get("active")):
            root_cause = "market_in_catalog_inactive"
            details = {"catalog": catalog_row}
        elif not bool(catalog_row.get("eligible")):
            root_cause = f"market_excluded:{catalog_row.get('eligibility_reason') or 'unknown'}"
            details = {"catalog": catalog_row}
        else:
            root_cause = "market_in_universe_without_scan_row"
            details = {"catalog": catalog_row}

        pattern = pattern_by_market.get(market_id, "unknown")
        root_cause_counts[root_cause] += 1
        pattern_counts[pattern] += 1
        classified_rows.append(
            {
                "timestamp_utc": trade_ts,
                "condition_id": market_id,
                "event_slug": trade.get("event_slug"),
                "city": trade.get("city"),
                "local_date": trade.get("local_date"),
                "bucket_label": trade.get("bucket_label"),
                "price": trade.get("price"),
                "size": trade.get("size"),
                "root_cause": root_cause,
                "pattern": pattern,
                "details": details,
            }
        )

    matched_ratio = (len(matched_rows) / len(trade_rows)) if trade_rows else 0.0
    return {
        "classified_rows": classified_rows,
        "summary": {
            "trade_count": len(trade_rows),
            "scan_row_count": len(market_scan_rows),
            "matched_trade_count": len(matched_rows),
            "matched_trade_ratio": round(matched_ratio, 6),
            "root_cause_counts": [
                {"root_cause": key, "count": count}
                for key, count in sorted(root_cause_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "pattern_counts": [
                {"pattern": key, "count": count}
                for key, count in sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        },
    }


def _build_markdown_report(*, comparison_result: dict[str, Any], parity: dict[str, Any]) -> str:
    summary = parity["summary"]
    window = comparison_result["window"]
    lines = [
        "# ColdMath Merge Parity",
        "",
        "## Window",
        f"- Start UTC: `{window['window_start_utc'].isoformat()}`",
        f"- End UTC: `{window['window_end_utc'].isoformat()}`",
        "",
        "## Summary",
        f"- ColdMath trade count: `{summary['trade_count']}`",
        f"- Merge scan rows: `{summary['scan_row_count']}`",
        f"- Matched trade count: `{summary['matched_trade_count']}`",
        f"- Matched trade ratio: `{summary['matched_trade_ratio']}`",
        "",
        "## Root Causes",
    ]
    root_causes = summary.get("root_cause_counts") or []
    if not root_causes:
        lines.append("- None")
    else:
        for item in root_causes:
            lines.append(f"- `{item['root_cause']}`: `{item['count']}`")

    lines.extend(["", "## Trade Patterns"])
    patterns = summary.get("pattern_counts") or []
    if not patterns:
        lines.append("- None")
    else:
        for item in patterns:
            lines.append(f"- `{item['pattern']}`: `{item['count']}`")

    lines.extend(["", "## Classified Trades"])
    if not parity["classified_rows"]:
        lines.append("- None")
    else:
        for row in parity["classified_rows"][:100]:
            price = safe_float(row.get("price"))
            price_text = f"{price:.4f}" if price is not None else "n/a"
            lines.append(
                "- "
                f"`{row['timestamp_utc'].isoformat()}` | "
                f"`{row['city']}` `{row['bucket_label']}` @ `{price_text}` | "
                f"`{row['pattern']}` | "
                f"`{row['root_cause']}`"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
