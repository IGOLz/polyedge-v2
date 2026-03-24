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
                m.health_data
            FROM weather_clone_market_scans m
            WHERE m.captured_at BETWEEN %s AND %s
            ORDER BY m.captured_at ASC
            """,
            (window_start_utc, window_end_utc),
        )
    finally:
        conn.close()
    return rows


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
            matched_trades.append(
                {
                    "timestamp_utc": trade_ts,
                    "market_id": trade_market,
                    "city": trade.get("city"),
                    "bucket_label": trade.get("bucket_label"),
                    "playbook_key": best_signal.get("playbook_key"),
                    "signal_time_utc": best_signal.get("captured_at"),
                    "delta_seconds": round(best_delta, 3),
                }
            )
        else:
            for row in nearby_nonqualifying:
                for reason in row.get("rejection_reasons") or []:
                    rejection_buckets[str(reason)] += 1
            missed_trades.append(
                {
                    "timestamp_utc": trade_ts,
                    "market_id": trade_market,
                    "city": trade.get("city"),
                    "bucket_label": trade.get("bucket_label"),
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
        "## Top Miss Reasons",
    ]
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
