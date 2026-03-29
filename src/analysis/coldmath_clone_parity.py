"""Compare ColdMath public trades with weather clone scan telemetry."""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from analysis.coldmath_window_compare import DEFAULT_LOG_PATH, run_window_comparison
from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.utils import ensure_dir

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure weather clone parity against ColdMath public trades")
    parser.add_argument("--profile", type=str, default="ColdMath")
    parser.add_argument("--wallet", type=str)
    parser.add_argument("--log-path", type=str, default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--fallback-log-path", type=str, default=None)
    parser.add_argument("--lxc-date-is", type=str, default=None)
    parser.add_argument("--log-timezone", type=str, default=None)
    parser.add_argument("--window-start-utc", type=str, default=None)
    parser.add_argument("--window-end-utc", type=str, default=None)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--heartbeat-gap-seconds", type=float, default=180.0)
    parser.add_argument("--match-window-seconds", type=float, default=15.0)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_clone_parity(args)
    logger.info("Clone parity complete with matched ratio %.4f", result["summary"]["matched_trade_ratio"])
    return 0


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def run_clone_parity(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
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
            window_start_utc=args.window_start_utc,
            window_end_utc=args.window_end_utc,
            window_hours=args.window_hours,
            heartbeat_gap_seconds=args.heartbeat_gap_seconds,
            output_dir=str(
                ensure_dir(
                    Path(args.output_dir).resolve()
                    if args.output_dir
                    else Path(__file__).resolve().parents[2] / "src" / "results" / "wallet_forensics" / "coldmath_clone_parity"
                )
            ),
            verbose=args.verbose,
        )
    )
    output_dir = Path(comparison_result["report_path"]).resolve().parent
    signals = _load_clone_signals(
        window_start_utc=comparison_result["window"]["window_start_utc"],
        window_end_utc=comparison_result["window"]["window_end_utc"],
    )
    parity = _match_signals_to_trades(
        trade_rows=comparison_result["coldmath"]["trade_rows"],
        signal_rows=signals,
        match_window_seconds=float(args.match_window_seconds),
    )
    report_path = output_dir / "coldmath_clone_parity_report.md"
    summary_path = output_dir / "coldmath_clone_parity_summary.json"
    report_path.write_text(
        _build_markdown_report(comparison_result=comparison_result, parity=parity),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(parity, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {
        "comparison_result": comparison_result,
        "signals": signals,
        "summary": parity["summary"],
        "report_path": str(report_path),
        "summary_path": str(summary_path),
    }


def _load_clone_signals(*, window_start_utc: datetime, window_end_utc: datetime) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = load_rows(
            conn,
            """
            SELECT
                m.captured_at,
                m.market_id,
                m.event_id,
                m.event_slug,
                m.city,
                m.local_date,
                m.bucket_label,
                m.playbook_key,
                m.side,
                m.qualifies,
                m.live_eligible,
                m.candidate_score,
                m.rejection_reasons,
                m.signal_data,
                m.sequence_data,
                m.health_data,
                c.execution_allowed,
                c.execution_health,
                c.market_data_health,
                c.summary_data->>'stand_down_reason' AS stand_down_reason,
                c.summary_data->>'guard_warning_reason' AS guard_warning_reason,
                c.summary_data->'wallet_guard' AS wallet_guard
            FROM weather_clone_market_scans m
            JOIN weather_clone_cycles c ON c.id = m.cycle_id
            WHERE m.captured_at BETWEEN %s AND %s
            ORDER BY m.captured_at ASC
            """,
            (window_start_utc, window_end_utc),
        )
    finally:
        conn.close()
    return rows


def _miss_classification(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "not_in_scope"

    rejection_reasons = {
        str(reason)
        for row in rows
        for reason in (row.get("rejection_reasons") or [])
        if str(reason)
    }
    stand_down_reasons = {
        str(row.get("stand_down_reason") or "")
        for row in rows
        if str(row.get("stand_down_reason") or "")
    }
    guard_warning_reasons = {
        str(row.get("guard_warning_reason") or "")
        for row in rows
        if str(row.get("guard_warning_reason") or "")
    }
    wallet_guard_reasons = {
        str((_maybe_json(row.get("wallet_guard")) or {}).get("reason") or "")
        for row in rows
        if str((_maybe_json(row.get("wallet_guard")) or {}).get("reason") or "")
    }
    if stand_down_reasons or guard_warning_reasons or wallet_guard_reasons:
        return "missed_by_guard"

    missing_data_reasons = {
        "missing_pair_ask",
        "missing_full_quote_pair",
        "missing_quote_time",
        "missing_directional_ask",
        "missing_complementary_ask",
        "stale_quote",
    }
    if rejection_reasons & missing_data_reasons:
        return "missed_by_missing_data"

    if any(not bool(row.get("execution_allowed")) for row in rows):
        return "missed_by_health"
    if any(str(row.get("execution_health") or "") not in {"", "healthy", "shadow_only"} for row in rows):
        return "missed_by_health"
    if any(str(row.get("market_data_health") or "") not in {"", "healthy"} for row in rows):
        return "missed_by_health"

    return "missed_by_rule"


def _match_signals_to_trades(
    *,
    trade_rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
    match_window_seconds: float,
) -> dict[str, Any]:
    qualifying_signals = [row for row in signal_rows if bool(row.get("qualifies"))]
    matched_trades: list[dict[str, Any]] = []
    missed_trades: list[dict[str, Any]] = []
    false_positive_conditions: set[tuple[str, str]] = set()
    matched_signal_ids: set[int] = set()
    time_deltas: list[float] = []

    rejection_buckets: dict[str, int] = defaultdict(int)
    classification_counts: dict[str, int] = defaultdict(int)
    playbook_metrics: dict[str, dict[str, int]] = defaultdict(
        lambda: {"trade_count": 0, "matched_trade_count": 0, "missed_trade_count": 0}
    )

    for trade in trade_rows:
        trade_ts = trade["timestamp_utc"]
        trade_market = str(trade.get("condition_id") or trade.get("market_id") or "")
        matching = []
        nearby_nonqualifying = []
        for idx, signal in enumerate(signal_rows):
            signal_market = str(signal.get("market_id") or "")
            if signal_market != trade_market:
                continue
            signal_ts = signal["captured_at"] if isinstance(signal["captured_at"], datetime) else signal["captured_at"]
            if not isinstance(signal_ts, datetime):
                continue
            delta = abs((signal_ts - trade_ts).total_seconds())
            if delta <= match_window_seconds and bool(signal.get("qualifies")):
                matching.append((delta, idx, signal))
            elif delta <= 60.0 and not bool(signal.get("qualifies")):
                nearby_nonqualifying.append(signal)
        if matching:
            matching.sort(key=lambda item: (item[0], -float(item[2].get("candidate_score") or 0.0)))
            best_delta, best_idx, best_signal = matching[0]
            matched_signal_ids.add(best_idx)
            time_deltas.append(best_delta)
            playbook_key = str(best_signal.get("playbook_key") or "unknown")
            classification_counts["matched"] += 1
            playbook_metrics[playbook_key]["trade_count"] += 1
            playbook_metrics[playbook_key]["matched_trade_count"] += 1
            matched_trades.append(
                {
                    "timestamp_utc": trade_ts,
                    "market_id": trade_market,
                    "city": trade.get("city"),
                    "bucket_label": trade.get("bucket_label"),
                    "playbook_key": playbook_key,
                    "signal_time_utc": best_signal.get("captured_at"),
                    "delta_seconds": round(best_delta, 3),
                    "classification": "matched",
                }
            )
        else:
            for row in nearby_nonqualifying:
                for reason in row.get("rejection_reasons") or []:
                    rejection_buckets[str(reason)] += 1
            classification = _miss_classification(nearby_nonqualifying)
            classification_counts[classification] += 1
            nearby_playbooks = sorted({str(row.get("playbook_key") or "unknown") for row in nearby_nonqualifying}) or ["unknown"]
            for playbook_key in nearby_playbooks:
                playbook_metrics[playbook_key]["trade_count"] += 1
                playbook_metrics[playbook_key]["missed_trade_count"] += 1
            missed_trades.append(
                {
                    "timestamp_utc": trade_ts,
                    "market_id": trade_market,
                    "city": trade.get("city"),
                    "bucket_label": trade.get("bucket_label"),
                    "classification": classification,
                    "playbook_keys": nearby_playbooks,
                    "rejection_reasons": sorted(
                        {str(reason) for row in nearby_nonqualifying for reason in (row.get("rejection_reasons") or [])}
                    ),
                }
            )

    traded_conditions = {
        (str(row.get("condition_id") or row.get("market_id") or ""), str(row.get("bucket_label") or ""))
        for row in trade_rows
    }
    for idx, signal in enumerate(qualifying_signals):
        signal_key = (str(signal.get("market_id") or ""), str(signal.get("bucket_label") or ""))
        if signal_key not in traded_conditions:
            false_positive_conditions.add(signal_key)

    matched_ratio = (len(matched_trades) / len(trade_rows)) if trade_rows else 0.0
    return {
        "matched_trades": matched_trades,
        "missed_trades": missed_trades,
        "summary": {
            "trade_count": len(trade_rows),
            "signal_count": len(signal_rows),
            "qualifying_signal_count": len(qualifying_signals),
            "matched_trade_count": len(matched_trades),
            "missed_high_confidence_trade_count": len(missed_trades),
            "false_positive_condition_count": len(false_positive_conditions),
            "matched_trade_ratio": round(matched_ratio, 6),
            "average_time_delta_seconds": round(sum(time_deltas) / len(time_deltas), 6) if time_deltas else None,
            "classification_counts": dict(sorted(classification_counts.items())),
            "playbook_metrics": [
                {"playbook_key": playbook_key, **metrics}
                for playbook_key, metrics in sorted(playbook_metrics.items())
            ],
            "top_miss_reasons": [
                {"reason": reason, "count": count}
                for reason, count in sorted(rejection_buckets.items(), key=lambda item: (-item[1], item[0]))[:10]
            ],
        },
    }


def _build_markdown_report(*, comparison_result: dict[str, Any], parity: dict[str, Any]) -> str:
    summary = parity["summary"]
    window = comparison_result["window"]
    lines = [
        "# ColdMath Clone Parity",
        "",
        "## Window",
        f"- Start UTC: `{window['window_start_utc'].isoformat()}`",
        f"- End UTC: `{window['window_end_utc'].isoformat()}`",
        "",
        "## Summary",
        f"- ColdMath trade count: `{summary['trade_count']}`",
        f"- Clone signal rows: `{summary['signal_count']}`",
        f"- Clone qualifying signal rows: `{summary['qualifying_signal_count']}`",
        f"- Matched trade count: `{summary['matched_trade_count']}`",
        f"- Missed high-confidence trade count: `{summary['missed_high_confidence_trade_count']}`",
        f"- False positive condition count: `{summary['false_positive_condition_count']}`",
        f"- Matched trade ratio: `{summary['matched_trade_ratio']}`",
        f"- Average time delta seconds: `{summary['average_time_delta_seconds']}`",
        "",
        "## Classification Counts",
    ]
    classification_counts = summary.get("classification_counts") or {}
    if not classification_counts:
        lines.append("- None")
    else:
        for classification, count in classification_counts.items():
            lines.append(f"- `{classification}`: `{count}`")

    lines.extend(
        [
            "",
            "## Playbook Metrics",
        ]
    )
    playbook_metrics = summary.get("playbook_metrics") or []
    if not playbook_metrics:
        lines.append("- None")
    else:
        for item in playbook_metrics:
            lines.append(
                f"- `{item['playbook_key']}`: trades=`{item['trade_count']}` matched=`{item['matched_trade_count']}` missed=`{item['missed_trade_count']}`"
            )

    lines.extend(
        [
            "",
        "## Top Miss Reasons",
        ]
    )
    top_reasons = summary.get("top_miss_reasons") or []
    if not top_reasons:
        lines.append("- None")
    else:
        for item in top_reasons:
            lines.append(f"- `{item['reason']}`: `{item['count']}`")

    lines.extend(["", "## Missed Trades"])
    if not parity["missed_trades"]:
        lines.append("- None")
    else:
        for row in parity["missed_trades"][:50]:
            lines.append(
                "- "
                f"`{row['timestamp_utc'].isoformat()}` | "
                f"`{row['city']}` `{row['bucket_label']}` | "
                f"`{row['market_id']}` | "
                f"`{row.get('classification')}` | "
                f"`{', '.join(row.get('rejection_reasons') or ['no_nearby_signal'])}`"
            )

    lines.extend(["", "## Matched Trades"])
    if not parity["matched_trades"]:
        lines.append("- None")
    else:
        for row in parity["matched_trades"][:50]:
            lines.append(
                "- "
                f"`{row['timestamp_utc'].isoformat()}` | "
                f"`{row['city']}` `{row['bucket_label']}` | "
                f"`{row['playbook_key']}` | "
                f"`delta={row['delta_seconds']}`"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
