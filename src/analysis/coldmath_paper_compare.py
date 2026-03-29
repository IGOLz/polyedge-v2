"""Compare weather paper-trading fills against ColdMath weather activity."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.db_sync import get_connection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare paper weather trades with ColdMath weather trades")
    parser.add_argument("--profile", type=str, default="ColdMath")
    parser.add_argument("--paper-run-id", type=str, default=None)
    parser.add_argument("--match-window-seconds", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    return parser


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _resolve_paper_run_id(cur, paper_run_id: str | None) -> str | None:
    if paper_run_id:
        cur.execute(
            "SELECT paper_run_id FROM weather_paper_cycles WHERE paper_run_id = %s ORDER BY captured_at DESC LIMIT 1",
            (paper_run_id,),
        )
    else:
        cur.execute(
            "SELECT paper_run_id FROM weather_paper_cycles ORDER BY captured_at DESC LIMIT 1"
        )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _resolve_profile_wallet(cur, profile: str) -> str | None:
    cur.execute(
        """
        SELECT proxy_wallet
        FROM wallet_tracker_watermark
        WHERE profile_name = %s
        """,
        (profile,),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])
    cur.execute(
        """
        SELECT proxy_wallet
        FROM wallet_targets
        WHERE profile_name = %s
        ORDER BY resolved_at DESC
        LIMIT 1
        """,
        (profile,),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _normalize_trade_type(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"buy", "bought"}:
        return "buy"
    if text in {"sell", "sold"}:
        return "sell"
    return None


def _normalize_outcome(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"yes", "up", "true"}:
        return "yes"
    if text in {"no", "down", "false"}:
        return "no"
    return None


def _load_paper_trades(cur, *, paper_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
            e.occurred_at,
            p.condition_id,
            p.event_slug,
            p.city,
            p.bucket_label,
            e.event_type,
            e.playbook_key,
            e.side,
            e.filled_shares,
            e.price,
            e.value_usd,
            e.raw_payload
        FROM weather_paper_position_events e
        JOIN weather_paper_positions p ON p.id = e.position_id
        WHERE e.paper_run_id = %s
          AND e.event_type IN ('order_fill', 'partial_fill', 'exit_fill')
        ORDER BY e.occurred_at ASC, e.id ASC
        """,
        (paper_run_id,),
    )
    rows: list[dict[str, Any]] = []
    for row in cur.fetchall():
        payload = _maybe_json(row[11]) or {}
        trade_type = _normalize_trade_type(payload.get("trade_type"))
        if trade_type is None:
            trade_type = "sell" if str(row[5] or "") == "exit_fill" else "buy"
        side = _normalize_outcome(row[7])
        if side is None:
            side = _normalize_outcome(payload.get("leg_side") or payload.get("side"))
        rows.append(
            {
                "timestamp_utc": row[0].astimezone(UTC),
                "condition_id": str(row[1] or ""),
                "event_slug": str(row[2] or ""),
                "city": str(row[3] or ""),
                "bucket_label": str(row[4] or ""),
                "playbook_key": str(row[6] or ""),
                "outcome": side,
                "trade_type": trade_type,
                "size": float(row[8] or 0.0),
                "price": float(row[9] or 0.0),
                "notional_usd": float(row[10] or 0.0),
            }
        )
    return [row for row in rows if row["condition_id"] and row["outcome"] and row["trade_type"]]


def _load_coldmath_trades(cur, *, profile: str, proxy_wallet: str, window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
            timestamp,
            condition_id,
            event_slug,
            title,
            side,
            outcome,
            size,
            usdc_size,
            price
        FROM wallet_tracker_activity
        WHERE profile_name = %s
          AND proxy_wallet = %s
          AND to_timestamp(timestamp) BETWEEN %s AND %s
          AND condition_id IS NOT NULL
        ORDER BY timestamp ASC
        """,
        (profile, proxy_wallet, window_start, window_end),
    )
    raw_rows = cur.fetchall()
    trade_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        trade_type = _normalize_trade_type(row[4])
        outcome = _normalize_outcome(row[5])
        if trade_type is None or outcome is None:
            continue
        trade_rows.append(
            {
                "timestamp_utc": datetime.fromtimestamp(int(row[0]), tz=UTC),
                "condition_id": str(row[1] or ""),
                "event_slug": str(row[2] or ""),
                "title": str(row[3] or ""),
                "trade_type": trade_type,
                "outcome": outcome,
                "size": float(row[6] or 0.0),
                "notional_usd": float(row[7] or 0.0) if row[7] is not None else float((row[6] or 0.0) * (row[8] or 0.0)),
                "price": float(row[8] or 0.0),
            }
        )
    return trade_rows


def _load_coldmath_playbooks(cur, *, proxy_wallet: str, window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT strategy_key, condition_id, event_slug, started_at, ended_at, confidence
        FROM wallet_playbook_sequences
        WHERE proxy_wallet = %s
          AND ended_at >= %s
          AND started_at <= %s
        ORDER BY started_at ASC
        """,
        (proxy_wallet, window_start, window_end),
    )
    rows = []
    for row in cur.fetchall():
        rows.append(
            {
                "strategy_key": str(row[0] or ""),
                "condition_id": str(row[1] or ""),
                "event_slug": str(row[2] or ""),
                "started_at": row[3].astimezone(UTC),
                "ended_at": row[4].astimezone(UTC),
                "confidence": float(row[5] or 0.0),
            }
        )
    return rows


def _attach_public_playbooks(trades: list[dict[str, Any]], sequences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for trade in trades:
        best: dict[str, Any] | None = None
        for sequence in sequences:
            if sequence["condition_id"] and sequence["condition_id"] != trade["condition_id"]:
                continue
            if sequence["event_slug"] and trade["event_slug"] and sequence["event_slug"] != trade["event_slug"]:
                continue
            if sequence["started_at"] <= trade["timestamp_utc"] <= sequence["ended_at"]:
                if best is None or sequence["confidence"] > best["confidence"]:
                    best = sequence
        trade["playbook_key"] = best["strategy_key"] if best else None
    return trades


def _match_trades(
    *,
    coldmath_trades: list[dict[str, Any]],
    paper_trades: list[dict[str, Any]],
    match_window_seconds: float,
) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    used_paper_ids: set[int] = set()
    notional_miss_rows: list[dict[str, Any]] = []
    time_deltas: list[float] = []
    size_errors: list[float] = []
    playbook_known = 0
    playbook_matched = 0

    for coldmath_trade in coldmath_trades:
        best_idx = None
        best_delta = None
        for idx, paper_trade in enumerate(paper_trades):
            if idx in used_paper_ids:
                continue
            if paper_trade["condition_id"] != coldmath_trade["condition_id"]:
                continue
            if paper_trade["outcome"] != coldmath_trade["outcome"]:
                continue
            if paper_trade["trade_type"] != coldmath_trade["trade_type"]:
                continue
            delta = abs((paper_trade["timestamp_utc"] - coldmath_trade["timestamp_utc"]).total_seconds())
            if delta > match_window_seconds:
                continue
            if best_delta is None or delta < best_delta:
                best_idx = idx
                best_delta = delta
        if best_idx is None:
            misses.append(coldmath_trade)
            notional_miss_rows.append(coldmath_trade)
            continue
        used_paper_ids.add(best_idx)
        paper_trade = paper_trades[best_idx]
        time_deltas.append(float(best_delta or 0.0))
        coldmath_size = max(float(coldmath_trade["size"] or 0.0), 1e-9)
        size_errors.append(abs(float(paper_trade["size"] or 0.0) - coldmath_size) / coldmath_size)
        if coldmath_trade.get("playbook_key"):
            playbook_known += 1
            if coldmath_trade["playbook_key"] == paper_trade["playbook_key"]:
                playbook_matched += 1
        matched.append(
            {
                "condition_id": coldmath_trade["condition_id"],
                "outcome": coldmath_trade["outcome"],
                "trade_type": coldmath_trade["trade_type"],
                "coldmath_time_utc": coldmath_trade["timestamp_utc"].isoformat(),
                "paper_time_utc": paper_trade["timestamp_utc"].isoformat(),
                "delta_seconds": round(float(best_delta or 0.0), 3),
                "coldmath_playbook_key": coldmath_trade.get("playbook_key"),
                "paper_playbook_key": paper_trade.get("playbook_key"),
            }
        )

    miss_counter = Counter()
    for row in misses:
        miss_counter["no_matching_paper_trade"] += 1

    return {
        "matched_rows": matched,
        "missed_rows": misses,
        "condition_side_match_rate": round(len(matched) / max(len(coldmath_trades), 1), 6),
        "playbook_match_rate": round(playbook_matched / max(playbook_known, 1), 6) if playbook_known else None,
        "median_entry_delta_seconds": round(sorted(time_deltas)[len(time_deltas) // 2], 6) if time_deltas else None,
        "median_size_error_ratio": round(sorted(size_errors)[len(size_errors) // 2], 6) if size_errors else None,
        "top_miss_reasons": [{"reason": reason, "count": count} for reason, count in miss_counter.most_common(5)],
        "top_notional_mismatches": sorted(notional_miss_rows, key=lambda item: float(item.get("notional_usd") or 0.0), reverse=True)[:10],
    }


def build_report(profile: str, paper_run_id: str | None, match_window_seconds: float) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            resolved_paper_run_id = _resolve_paper_run_id(cur, paper_run_id)
            if not resolved_paper_run_id:
                raise RuntimeError("No paper run found")
            proxy_wallet = _resolve_profile_wallet(cur, profile)
            if not proxy_wallet:
                raise RuntimeError(f"Could not resolve wallet for profile '{profile}'")
            paper_trades = _load_paper_trades(cur, paper_run_id=resolved_paper_run_id)
            if not paper_trades:
                raise RuntimeError(f"No paper trades found for run '{resolved_paper_run_id}'")
            window_start = paper_trades[0]["timestamp_utc"]
            window_end = paper_trades[-1]["timestamp_utc"]
            coldmath_trades = _load_coldmath_trades(cur, profile=profile, proxy_wallet=proxy_wallet, window_start=window_start, window_end=window_end)
            sequences = _load_coldmath_playbooks(cur, proxy_wallet=proxy_wallet, window_start=window_start, window_end=window_end)
            coldmath_trades = _attach_public_playbooks(coldmath_trades, sequences)
            parity = _match_trades(coldmath_trades=coldmath_trades, paper_trades=paper_trades, match_window_seconds=match_window_seconds)
            cur.execute(
                """
                SELECT captured_at, realized_pnl_usd, unrealized_pnl_usd, equity_pnl_usd
                FROM weather_paper_equity_snapshots
                WHERE paper_run_id = %s
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (resolved_paper_run_id,),
            )
            equity_row = cur.fetchone()
    finally:
        conn.close()

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "paper_run_id": resolved_paper_run_id,
        "comparison_scope": "weather_only_overlapping_window_only",
        "window_start_utc": window_start.isoformat(),
        "window_end_utc": window_end.isoformat(),
        "paper_trade_count": len(paper_trades),
        "coldmath_trade_count": len(coldmath_trades),
        "paper_equity_pnl_usd": float(equity_row[3] or 0.0) if equity_row else None,
        "paper_realized_pnl_usd": float(equity_row[1] or 0.0) if equity_row else None,
        "paper_unrealized_pnl_usd": float(equity_row[2] or 0.0) if equity_row else None,
        "condition_side_match_rate": parity["condition_side_match_rate"],
        "playbook_match_rate": parity["playbook_match_rate"],
        "median_entry_delta_seconds": parity["median_entry_delta_seconds"],
        "median_size_error_ratio": parity["median_size_error_ratio"],
        "top_miss_reasons": parity["top_miss_reasons"],
        "top_notional_mismatches": parity["top_notional_mismatches"],
        "matched_rows": parity["matched_rows"],
    }
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ColdMath Paper Comparison",
        "",
        "- Scope: `weather_only_overlapping_window_only`",
        f"- Paper run: `{report['paper_run_id']}`",
        f"- Window UTC: `{report['window_start_utc']}` to `{report['window_end_utc']}`",
        f"- Paper trades: `{report['paper_trade_count']}`",
        f"- ColdMath trades: `{report['coldmath_trade_count']}`",
        f"- Paper equity PnL USD: `{report['paper_equity_pnl_usd']}`",
        f"- Condition+side match rate: `{report['condition_side_match_rate']}`",
        f"- Playbook match rate: `{report['playbook_match_rate']}`",
        f"- Median entry delta seconds: `{report['median_entry_delta_seconds']}`",
        f"- Median size error ratio: `{report['median_size_error_ratio']}`",
    ]
    if report["top_miss_reasons"]:
        lines.append("- Top miss reasons: `" + ", ".join(f"{item['reason']}:{item['count']}" for item in report["top_miss_reasons"]) + "`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.profile, args.paper_run_id, args.match_window_seconds)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(_render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
